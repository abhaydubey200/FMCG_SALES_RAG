"""
Keyword (lexical) search via BM25.

Why keyword search matters even with vector search available: TF-IDF/
neural vectors can miss exact-match signals that matter a lot in a
business/compliance context — e.g. a query for "15%" or a specific
campaign_id/product name benefits from exact lexical matching, whereas a
pure vector search can dilute that signal across "similar" chunks. BM25
is the standard for this and is cheap to run alongside vector search.
"""
import re
from dataclasses import dataclass
from typing import List

from rank_bm25 import BM25Okapi

from src import config
from src.ingestion.document_loader import Chunk


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9%]+", text.lower())


@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float


class KeywordIndex:
    def __init__(self):
        self.chunks: List[Chunk] = []
        self.bm25: BM25Okapi = None

    def build(self, chunks: List[Chunk]):
        self.chunks = chunks
        tokenized = [_tokenize(c.text) for c in chunks]
        self.bm25 = BM25Okapi(tokenized)

    def search(self, query: str, top_k: int = None) -> List[ScoredChunk]:
        top_k = top_k or config.TOP_K_KEYWORD
        if self.bm25 is None:
            return []
        scores = self.bm25.get_scores(_tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]
        return [ScoredChunk(chunk=self.chunks[i], score=float(scores[i])) for i in ranked if scores[i] > 0]
