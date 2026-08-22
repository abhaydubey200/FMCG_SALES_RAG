"""
Document ingestion: load -> extract -> clean -> chunk -> (embed happens in
retrieval/vector_store.py, kept separate so ingestion doesn't need to know
which embedding backend is active).

Chunking strategy (documented in README "Chunking strategy"):
We chunk on markdown section boundaries (## headers) first, then apply a
word-count sliding window *within* a section if the section itself is long.
This keeps each chunk topically coherent (a chunk is never a mix of two
unrelated sections) while still bounding chunk size for retrieval quality
and LLM context budget. Overlap prevents a fact that straddles a chunk
boundary from being unretrievable.
"""
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from src import config


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    document_name: str
    document_type: str
    section: str
    text: str
    metadata: dict = field(default_factory=dict)


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_sections(text: str):
    """Split a markdown doc into (section_title, section_body) on ## headers."""
    parts = re.split(r"\n(?=## )", text)
    sections = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.split("\n", 1)
        header = lines[0].lstrip("#").strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        if part.startswith("# ") and not part.startswith("## "):
            # top-level title line before first ## section; skip as its own chunk
            continue
        sections.append((header or "Document", body))
    return sections


def _word_window_chunks(text: str, size: int, overlap: int) -> List[str]:
    words = text.split()
    if len(words) <= size:
        return [text] if text else []
    chunks = []
    step = max(1, size - overlap)
    for start in range(0, len(words), step):
        window = words[start:start + size]
        if not window:
            break
        chunks.append(" ".join(window))
        if start + size >= len(words):
            break
    return chunks


def load_and_chunk_document(path: Path, document_type: str = "policy") -> List[Chunk]:
    raw = path.read_text(encoding="utf-8")
    cleaned = _clean_text(raw)
    document_id = path.stem
    document_name = path.stem.replace("_", " ").title()

    sections = _split_sections(cleaned)
    chunks: List[Chunk] = []
    for section_title, body in sections:
        if not body:
            continue
        for piece in _word_window_chunks(body, config.CHUNK_SIZE_WORDS, config.CHUNK_OVERLAP_WORDS):
            chunk_id = f"{document_id}__{uuid.uuid4().hex[:8]}"
            chunks.append(Chunk(
                chunk_id=chunk_id,
                document_id=document_id,
                document_name=document_name,
                document_type=document_type,
                section=section_title,
                text=f"{section_title}: {piece}",
                metadata={
                    "source_path": str(path),
                },
            ))
    return chunks


def load_knowledge_base(kb_dir: Path = None) -> List[Chunk]:
    kb_dir = kb_dir or config.KB_DIR
    all_chunks: List[Chunk] = []
    for path in sorted(Path(kb_dir).glob("*.md")):
        all_chunks.extend(load_and_chunk_document(path))
    return all_chunks


if __name__ == "__main__":
    chunks = load_knowledge_base()
    print(f"Loaded {len(chunks)} chunks from {config.KB_DIR}")
    for c in chunks[:3]:
        print("---")
        print(c.chunk_id, c.document_name, c.section)
        print(c.text[:200])
