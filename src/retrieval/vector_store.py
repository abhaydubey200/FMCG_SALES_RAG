"""
Vector store built on top of the pluggable embedder.

In a production deployment this class's on-disk pickle would be replaced
by PostgreSQL + pgvector (per assignment Section 19 "Preferred" stack) or
Qdrant/Chroma/FAISS — the interface (add, search) is intentionally the
same shape those clients expose, so the storage backend is swappable
without touching the retriever or RAG pipeline.
"""
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np

from src import config
from src.ingestion.document_loader import Chunk
from src.retrieval.embeddings import get_embedder


@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float


class VectorStore:
    def __init__(self):
        self.embedder = get_embedder()
        self.chunks: List[Chunk] = []
        self.vectors: np.ndarray = None

    def build(self, chunks: List[Chunk]):
        self.chunks = chunks
        texts = [c.text for c in chunks]
        self.embedder.fit(texts)
        self.vectors = self.embedder.embed(texts)

    def save(self, path: Path = None):
        path = path or config.VECTOR_STORE_PATH
        with open(path, "wb") as f:
            pickle.dump({"chunks": self.chunks, "vectors": self.vectors, "embedder": self.embedder}, f)

    def load(self, path: Path = None):
        path = path or config.VECTOR_STORE_PATH
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.chunks = data["chunks"]
        self.vectors = data["vectors"]
        self.embedder = data["embedder"]
        return self

    def search(self, query: str, top_k: int = None) -> List[ScoredChunk]:
        top_k = top_k or config.TOP_K_VECTOR
        if self.vectors is None or len(self.chunks) == 0:
            return []
        q_vec = self.embedder.embed([query])[0]
        # cosine similarity (vectors are already L2-normalized)
        sims = self.vectors @ q_vec
        top_idx = np.argsort(-sims)[:top_k]
        return [ScoredChunk(chunk=self.chunks[i], score=float(sims[i])) for i in top_idx if sims[i] > 0]


def build_and_persist_vector_store() -> VectorStore:
    from src.ingestion.document_loader import load_knowledge_base
    chunks = load_knowledge_base()
    store = VectorStore()
    store.build(chunks)
    store.save()
    print(f"Vector store built: {len(chunks)} chunks, dim={store.embedder.dim} -> {config.VECTOR_STORE_PATH}")
    return store


if __name__ == "__main__":
    store = build_and_persist_vector_store()
    results = store.search("What discount is recommended for campaigns?", top_k=3)
    for r in results:
        print(round(r.score, 3), r.chunk.document_name, r.chunk.section)
