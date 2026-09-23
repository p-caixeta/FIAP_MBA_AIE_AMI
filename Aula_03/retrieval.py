"""Recuperação TF-IDF com filtros confiáveis antes do ranking."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config import AS_OF, MAX_TOP_K, TENANT_ID, TOP_K


DATA_DIR = Path(__file__).resolve().parent / "dados"


def _load_json(name: str):
    with (DATA_DIR / name).open(encoding="utf-8") as file:
        return json.load(file)


def eligible_chunks(chunks: list[dict], manifest: list[dict]) -> list[dict]:
    """Aplica tenant, publicação e vigência antes de construir o índice."""
    documents = {item["doc_id"]: item for item in manifest}
    selected = []
    for chunk in chunks:
        document = documents.get(chunk["doc_id"], {})
        is_current = (
            document.get("tenant_id") == TENANT_ID
            and document.get("status") == "published"
            and document.get("valid_from", "9999-12-31") <= AS_OF
            and (document.get("valid_to") is None or AS_OF < document["valid_to"])
        )
        if is_current:
            selected.append({**deepcopy(document), **deepcopy(chunk)})
    return selected


def build_index(chunks: list[dict]):
    """Constrói uma vez o índice pequeno do laboratório."""
    vectorizer = TfidfVectorizer(strip_accents="unicode", ngram_range=(1, 2))
    matrix = vectorizer.fit_transform([chunk["text"] for chunk in chunks])
    return vectorizer, matrix


MANIFEST = _load_json("corpus_manifest.json")
CHUNKS = eligible_chunks(_load_json("chunks.json"), MANIFEST)
VECTORIZER, MATRIX = build_index(CHUNKS)


def build_query(request: str, order: dict | None, logistics: dict | None, resolution: dict | None) -> str:
    """Ponto didático editável: junta a pergunta aos fatos confirmados disponíveis."""
    terms = [request.strip()]
    if logistics and logistics.get("status"):
        terms.append(f"status operacional {logistics['status']}")
    if logistics and logistics.get("eta"):
        terms.append(str(logistics["eta"]))
    if order and order.get("modality"):
        terms.append(f"modalidade {order['modality']}")
    if resolution and resolution.get("error"):
        terms.append("orientação diante de falha operacional")
    return " ".join(terms)


def search_policies(query: str, top_k: int = TOP_K) -> dict:
    """Busca políticas elegíveis e devolve texto integral, versão e proveniência."""
    if not isinstance(query, str) or not query.strip():
        return {"query": str(query), "status": "invalid_query", "hits": [], "top_k": TOP_K}
    limit = min(max(1, int(top_k)), MAX_TOP_K)
    query_vector = VECTORIZER.transform([query])
    scores = cosine_similarity(query_vector, MATRIX).ravel()
    ranked = sorted(
        ((float(score), item) for score, item in zip(scores, CHUNKS) if score > 0),
        key=lambda pair: (-pair[0], pair[1]["chunk_id"]),
    )
    hits = []
    for score, item in ranked[:limit]:
        hits.append(
            {
                "doc_id": item["doc_id"],
                "chunk_id": item["chunk_id"],
                "title": item.get("title", item["doc_id"]),
                "section": item["section"],
                "text": item["text"],
                "version": item["version"],
                "score": round(score, 6),
                "source_path": item["source_path"],
                "source_url": item.get("source_url"),
                "tenant_id": item["tenant_id"],
                "status": item["status"],
                "valid_from": item["valid_from"],
                "valid_to": item.get("valid_to"),
            }
        )
    return {"query": query, "status": "ok" if hits else "no_results", "hits": hits, "top_k": limit}
