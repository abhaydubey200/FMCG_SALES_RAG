"""
Local file cleanup — removes seed data files.

Removes:
1. data/warehouse.db (SQLite seed data)
2. data/knowledge_base/*.pdf (seed documents)
3. data/knowledge_base/*.md (seed documents)
4. data/vector_store.pkl (cached vector store)
5. data/documents/* (seed documents)

This script does NOT remove user-uploaded data that has been
processed into PostgreSQL.
"""
import os
import shutil
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config


def clean_local_files():
    """Remove all local seed data files."""
    print("=== CLEANING LOCAL FILES ===\n")

    cleaned = 0

    # 1. Remove SQLite database
    db_path = Path(config.DB_PATH)
    if db_path.exists():
        size = db_path.stat().st_size
        db_path.unlink()
        print(f"  Removed: {db_path} ({size:,} bytes)")
        cleaned += 1

    # 2. Remove vector store
    vs_path = Path(config.VECTOR_STORE_PATH)
    if vs_path.exists():
        size = vs_path.stat().st_size
        vs_path.unlink()
        print(f"  Removed: {vs_path} ({size:,} bytes)")
        cleaned += 1

    # 3. Remove knowledge base files (seed documents only)
    kb_dir = Path(config.KB_DIR)
    if kb_dir.exists():
        seed_files = ["campaign_performance_guidelines.pdf", "Sales Order Sample Live Data.md"]
        for f in kb_dir.iterdir():
            if f.is_file() and (f.name in seed_files or f.name.endswith(('.pdf', '.md', '.txt'))):
                size = f.stat().st_size
                f.unlink()
                print(f"  Removed: {f.name} ({size:,} bytes)")
                cleaned += 1

    # 4. Remove documents directory contents
    docs_dir = Path(config.DOCUMENTS_DIR)
    if docs_dir.exists():
        for f in docs_dir.iterdir():
            if f.is_file():
                f.unlink()
                print(f"  Removed: documents/{f.name}")
                cleaned += 1

    # 5. Remove evaluation results (if any)
    eval_path = Path("src/evaluation/eval_results.json")
    if eval_path.exists():
        eval_path.unlink()
        print(f"  Removed: eval_results.json")
        cleaned += 1

    print(f"\n=== CLEANED {cleaned} FILES ===")
    print(f"  Knowledge base: {kb_dir} (empty)")
    print(f"  Vector store: removed")
    print(f"  SQLite DB: removed")
    print(f"\n  PostgreSQL remains the source of truth.")


if __name__ == "__main__":
    clean_local_files()
