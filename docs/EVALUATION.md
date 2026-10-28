# Evaluation report — NIST SP 800-82 Rev. 3

Executed on 2026-10-28 in the Manus Linux sandbox using Python 3.12.3, CPU inference, FastEmbed ONNX, `BAAI/bge-small-en-v1.5`, and Qdrant local mode. The downloaded source matched SHA-256 `608f554514d381853e24e0b33123b7080fbd757826f460032690aade63394616`; extraction found text on all 316 physical PDF pages and indexing created 652 page-aware chunks. No GPU or generative model was used. The complete run-specific machine-readable output is reproducible with `python scripts/evaluate.py` and is saved locally at `reports/evaluation.json` (ignored by Git because it embeds machine- and corpus-specific execution details).

The question set is seven hand-reviewed queries: five answerable items with one manually referenced PDF page each, plus two unanswerable questions. Relevant-page labels use 1-based physical PDF page indices. Retrieval cutoffs are chunk positions, not distinct pages. Recall@5 counts unique referenced pages found within the five chunks; Precision@5 counts retrieved chunks whose page is a reference page divided by five; MRR uses the first relevant chunk; nDCG@5 uses binary page relevance. Metrics are macro averages over the five answerable prompts.

| Method | Recall@5 | Precision@5 | MRR | nDCG@5 |
|---|---:|---:|---:|---:|
| BM25 | 0.8000 | 0.2400 | 0.8000 | 1.0000 |
| Dense cosine | 0.8000 | 0.2400 | 0.6667 | 0.9000 |
| Balanced RRF hybrid | 0.8000 | 0.2400 | 0.6667 | 0.9262 |

The actual app abstention threshold is dense top cosine 0.72. Observed answerability confusion on these seven questions was TP=5, FP=0, TN=2, FN=0 (7/7; 1.0000 accuracy). **This is in-sample and must not be read as an independent accuracy estimate:** the threshold was raised after an initial run on these same questions had two false positives. A new, held-out set is needed before selecting a production cutoff.

All five answerable prompts returned citations; neither unanswerable prompt returned one, so the combined expected-behavior coverage was 7/7 (1.0000). All returned citation IDs pointed to actual indexed chunks and the expected document title (1.0000 target provenance). The ask path promotes the top BM25 passage, then fills evidence from the balanced RRF list, and quotes up to three selected passages. Exact physical-page agreement with the one manually recorded reference was only 7 of 15 returned citation pages (0.4667). This low page-match result is an important known failure signal, not something to conceal: citations are real source locations, but top evidence is not reliably the adjudicated page for every query. The page metric also undercounts valid adjacent-page support and does not evaluate semantic entailment. The answer mode quotes retrieved text, but an evidence quote can be irrelevant or incomplete; humans must verify it.

Measured ranking latency averaged 138.87 ms and p95 was 164.70 ms across seven warm local CPU retrieval calls, including the tenant chunk scroll, query embedding, dense Qdrant query, BM25, and fusion; it excludes process/model startup, upload/indexing, and browser/network latency. Treat these numbers as a single small local run, not an SLO or comparative benchmark.

Reproduce from a clean environment with:

```bash
pip install -e '.[test]'
python scripts/download_data.py
python scripts/index_documents.py
python scripts/evaluate.py
```

Future evaluation should add at least a held-out set spanning additional documents, multiple judged pages per question, graded relevance, annotator agreement, claim-level faithfulness and abstention calibration, and latency over repeated runs. Do not use the current threshold or results for operational or safety-critical deployments.
