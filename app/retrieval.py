from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from typing import Any

from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

COLLECTION = "engineering_chunks"


def terms(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9._/-]*", text.lower())


def bm25_scores(
    query: str, corpus: list[dict[str, Any]], k1: float = 1.5, b: float = 0.75
) -> list[float]:
    q = terms(query)
    tokenized = [terms(c["text"]) for c in corpus]
    if not q or not tokenized:
        return [0.0] * len(corpus)
    avg_len = sum(map(len, tokenized)) / len(tokenized) or 1.0
    dfs = Counter(term for doc in tokenized for term in set(doc))
    n = len(tokenized)
    scores: list[float] = []
    for doc in tokenized:
        counts = Counter(doc)
        score = 0.0
        for term in q:
            df = dfs.get(term, 0)
            if not df:
                continue
            idf = max(0.0, math.log(1 + (n - df + 0.5) / (df + 0.5)))
            freq = counts[term]
            score += idf * freq * (k1 + 1) / (freq + k1 * (1 - b + b * len(doc) / avg_len))
        scores.append(score)
    return scores


class HybridRetriever:
    def __init__(self, settings):
        self.settings = settings
        self.embedder = TextEmbedding(model_name=settings.embedding_model)
        self.client = (
            QdrantClient(url=settings.qdrant_url)
            if settings.qdrant_url
            else QdrantClient(path=str(settings.qdrant_path))
        )
        self.dimension = next(iter(self.embedder.query_embed("dimension probe"))).shape[0]
        if not self.client.collection_exists(COLLECTION):
            self.client.create_collection(
                collection_name=COLLECTION,
                vectors_config=models.VectorParams(
                    size=self.dimension, distance=models.Distance.COSINE
                ),
            )

    def add_document(
        self,
        tenant_id: str,
        document_id: str,
        title: str,
        version: int,
        sha256: str,
        chunks: list[dict],
    ) -> None:
        vectors = list(self.embedder.passage_embed([c["text"] for c in chunks]))
        points = []
        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{tenant_id}:{document_id}:{index}"))
            payload = {
                **chunk,
                "tenant_id": tenant_id,
                "document_id": document_id,
                "title": title,
                "version": version,
                "sha256": sha256,
                "chunk_index": index,
                "is_current": True,
                "point_id": point_id,
            }
            points.append(models.PointStruct(id=point_id, vector=vector.tolist(), payload=payload))
        self.client.upsert(collection_name=COLLECTION, points=points, wait=True)

    def mark_document_obsolete(self, tenant_id: str, document_id: str) -> None:
        self.client.set_payload(
            collection_name=COLLECTION,
            payload={"is_current": False},
            points=models.Filter(
                must=[
                    models.FieldCondition(
                        key="tenant_id", match=models.MatchValue(value=tenant_id)
                    ),
                    models.FieldCondition(
                        key="document_id", match=models.MatchValue(value=document_id)
                    ),
                ]
            ),
            wait=True,
        )

    def all_chunks(self, tenant_id: str) -> list[dict]:
        flt = models.Filter(
            must=[
                models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant_id)),
                models.FieldCondition(key="is_current", match=models.MatchValue(value=True)),
            ]
        )
        result, _ = self.client.scroll(
            COLLECTION, scroll_filter=flt, limit=10000, with_payload=True, with_vectors=False
        )
        return [dict(point.payload or {}) for point in result]

    def ranked_lists(
        self, tenant_id: str, query: str, limit: int = 20
    ) -> tuple[dict[str, list[dict]], float]:
        chunks = self.all_chunks(tenant_id)
        if not chunks:
            return {"bm25": [], "dense": [], "hybrid": []}, 0.0
        vector = next(iter(self.embedder.query_embed(query))).tolist()
        flt = models.Filter(
            must=[
                models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant_id)),
                models.FieldCondition(key="is_current", match=models.MatchValue(value=True)),
            ]
        )
        dense = self.client.query_points(
            COLLECTION, query=vector, query_filter=flt, limit=max(limit, 20), with_payload=True
        ).points
        dense_ids = [p.payload["point_id"] for p in dense if p.payload]
        dense_top_score = float(dense[0].score) if dense else 0.0
        lexical_scores = bm25_scores(query, chunks)
        bm25_sorted = sorted(range(len(chunks)), key=lambda i: lexical_scores[i], reverse=True)
        bm25_ids = [chunks[i]["point_id"] for i in bm25_sorted if lexical_scores[i] > 0]
        by_id = {c["point_id"]: c for c in chunks}
        ranks: dict[str, float] = {}
        for result_ids in (dense_ids, bm25_ids):
            for rank, item_id in enumerate(result_ids, 1):
                ranks[item_id] = ranks.get(item_id, 0.0) + 1.0 / (60 + rank)
        hybrid_ids = sorted(ranks, key=ranks.get, reverse=True)[:limit]
        return {
            "bm25": [by_id[i] for i in bm25_ids[:limit]],
            "dense": [by_id[i] for i in dense_ids[:limit]],
            "hybrid": [{**by_id[i], "score": ranks[i]} for i in hybrid_ids],
        }, dense_top_score

    def search(
        self, tenant_id: str, query: str, top_k: int = 5
    ) -> tuple[list[dict], dict[str, float]]:
        ranked, dense_top_score = self.ranked_lists(tenant_id, query, max(20, top_k))
        results = [{**item, "citation_id": item["point_id"]} for item in ranked["hybrid"][:top_k]]
        return results, {
            "dense_top_score": dense_top_score,
            "bm25_candidates": float(len(ranked["bm25"])),
        }

    def close(self) -> None:
        self.client.close()
