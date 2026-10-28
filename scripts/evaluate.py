from __future__ import annotations

import json
import math
import time
from collections import defaultdict
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import ABSTENTION_DENSE_THRESHOLD, create_app

ROOT = Path(__file__).resolve().parents[1]


def ranking_metrics(ranked: list[dict], relevant_pages: set[int], k: int = 5) -> dict[str, float]:
    top = ranked[:k]
    flags = [int(item.get("page") in relevant_pages) for item in top]
    unique_found = {item.get("page") for item in top if item.get("page") in relevant_pages}
    first = next((i + 1 for i, flag in enumerate(flags) if flag), None)
    dcg = sum(flag / math.log2(i + 2) for i, flag in enumerate(flags))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(relevant_pages))))
    return {
        f"recall@{k}": len(unique_found) / max(len(relevant_pages), 1),
        f"precision@{k}": sum(flags) / k,
        "mrr": 1.0 / first if first else 0.0,
        f"ndcg@{k}": dcg / ideal if ideal else 0.0,
    }


def main() -> None:
    questions = json.loads((ROOT / "evaluation/questions.json").read_text())
    settings = Settings.from_env()
    admin = next(key for key, identity in settings.api_keys.items() if identity.role == "admin")
    app = create_app(settings)
    aggregated: dict[str, list[dict[str, float]]] = defaultdict(list)
    latency: list[float] = []
    answerable_counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    citation_supported: list[int] = []
    citation_page_match: list[int] = []
    citation_coverage: list[int] = []
    per_question: list[dict] = []
    indexed = False
    with TestClient(app) as client:
        # Re-indexing the exact sample is idempotent by content hash.
        source = ROOT / "data/raw/NIST.SP.800-82r3.pdf"
        if not source.exists():
            raise SystemExit("Missing data/raw/NIST.SP.800-82r3.pdf; run scripts/download_data.py")
        with source.open("rb") as stream:
            result = client.post(
                "/api/v1/documents/upload",
                headers={"X-API-Key": admin},
                files={"file": (source.name, stream, "application/pdf")},
            )
        if result.status_code not in (200, 201):
            raise SystemExit(f"Sample indexing failed: {result.status_code} {result.text}")
        svc = app.state.service
        for item in questions["questions"]:
            start = time.perf_counter()
            rankings, dense_score = svc.retriever.ranked_lists("demo", item["question"], 20)
            latency.append((time.perf_counter() - start) * 1000)
            relevant = set(item["relevant_pdf_pages"])
            if item["answerable"]:
                for method in ("bm25", "dense", "hybrid"):
                    aggregated[method].append(ranking_metrics(rankings[method], relevant, 5))
            predicted = dense_score >= ABSTENTION_DENSE_THRESHOLD
            actual = item["answerable"]
            key = "tp" if actual and predicted else "fn" if actual else "fp" if predicted else "tn"
            answerable_counts[key] += 1
            ask = client.post(
                "/api/v1/ask",
                headers={"X-API-Key": admin},
                json={"query": item["question"], "top_k": 5},
            )
            response = ask.json()
            citation_coverage.append(
                int(bool(response["citations"]) if actual else not response["citations"])
            )
            if actual:
                candidate_ids = {
                    chunk["point_id"] for method in ("hybrid", "bm25") for chunk in rankings[method]
                }
                supported = bool(response["citations"]) and all(
                    c["citation_id"] in candidate_ids and c["title"] == "NIST.SP.800-82r3.pdf"
                    for c in response["citations"]
                )
                citation_supported.append(int(supported))
                citation_page_match.extend(
                    int(c["page"] in relevant) for c in response["citations"]
                )
            per_question.append(
                {
                    "id": item["id"],
                    "answerable": actual,
                    "dense_top_score": round(dense_score, 4),
                    "predicted_answerable": not response["abstained"],
                    "retrieval_top5_pages": [row.get("page") for row in rankings["hybrid"][:5]],
                    "citation_count": len(response["citations"]),
                }
            )
        indexed = True
    methods = {
        method: {key: round(sum(row[key] for row in rows) / len(rows), 4) for key in rows[0]}
        for method, rows in aggregated.items()
    }
    n = len(questions["questions"])
    report = {
        "evaluation_version": questions["version"],
        "dataset_sha256": __import__("hashlib")
        .sha256((ROOT / "data/raw/NIST.SP.800-82r3.pdf").read_bytes())
        .hexdigest(),
        "question_count": n,
        "answerable_query_count": len(aggregated["hybrid"]),
        "unanswerable_query_count": sum(not q["answerable"] for q in questions["questions"]),
        "methods": methods,
        "answerability_confusion": answerable_counts,
        "answerability_accuracy": round((answerable_counts["tp"] + answerable_counts["tn"]) / n, 4),
        "citation_target_supported_rate": round(
            sum(citation_supported) / max(len(citation_supported), 1), 4
        ),
        "citation_coverage": round(sum(citation_coverage) / max(len(citation_coverage), 1), 4),
        "citation_relevant_page_rate": round(
            sum(citation_page_match) / max(len(citation_page_match), 1), 4
        ),
        "citation_measurement": (
            "Target support verifies IDs and title against indexed hybrid candidates; "
            "relevant-page rate compares cited physical PDF pages to manually judged page "
            "labels. Neither proves semantic entailment."
        ),
        "retrieval_latency_ms_mean": round(sum(latency) / len(latency), 2),
        "retrieval_latency_ms_p95": round(
            sorted(latency)[max(0, math.ceil(0.95 * len(latency)) - 1)], 2
        ),
        "answerability_threshold_dense_cosine": ABSTENTION_DENSE_THRESHOLD,
        "per_question": per_question,
        "indexed_sample": indexed,
        "environment": {
            "python": __import__("platform").python_version(),
            "platform": __import__("platform").platform(),
            "embedding_model": settings.embedding_model,
            "device": "CPU via FastEmbed/ONNX",
        },
        "limitations": [
            "Small manually reviewed single-document sample; not a representative benchmark.",
            "Abstention cutoff was adjusted after the first evaluation run using these same "
            "seven questions; answerability accuracy is in-sample and optimistic, not a "
            "holdout estimate.",
            "Page labels are 1-based physical PDF page indexes; duplicate retrieved chunks on "
            "one page can affect precision.",
            "Citation provenance and page match do not establish semantic faithfulness; answer "
            "mode is extractive and still needs human review.",
        ],
    }
    out = ROOT / "reports/evaluation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
