"""
Background worker for long-running operations.

Processes jobs from Redis queues:
- document_ingestion: PDF/TXT/MD parsing, chunking, embedding, indexing
- data_processing: CSV/XLSX profiling, validation, storage

Architecture:
  API → Redis Queue → Worker → Process → PostgreSQL
"""
import json
import logging
import os
import sys
import time
from pathlib import Path

import redis

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config
from src.ingestion.document_loader import load_and_chunk_document
from src.retrieval.vector_store import VectorStore

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("worker")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_DOCUMENT = "queue:document_ingestion"
QUEUE_DATA = "queue:data_processing"

# Job statuses
STATUS_QUEUED = "queued"
STATUS_PROCESSING = "processing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"


def get_redis():
    return redis.from_url(REDIS_URL, decode_responses=True)


def _store_job_status(rds, job_id, status, extra=None):
    """Update job status in Redis with optional extra fields."""
    rds.hset(f"job:{job_id}", "status", status)
    rds.hset(f"job:{job_id}", "updated_at", str(time.time()))
    if extra:
        for k, v in extra.items():
            rds.hset(f"job:{job_id}", k, str(v)[:500])


def process_document_job(job: dict, rds):
    """Process a document ingestion job: parse → chunk → embed → index."""
    doc_id = job.get("document_id")
    file_path = job.get("file_path")
    doc_type = job.get("document_type", "policy")

    logger.info(f"Processing document: {doc_id} ({file_path})")

    try:
        _store_job_status(rds, doc_id, STATUS_PROCESSING)

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Chunk
        chunks = load_and_chunk_document(path, doc_type)
        logger.info(f"Created {len(chunks)} chunks for {doc_id}")

        # Embed + index into vector store
        store = VectorStore()
        if Path(config.VECTOR_STORE_PATH).exists():
            store.load()
        store.build(chunks)
        store.save()

        # Store document metadata in PostgreSQL if available
        if config.USE_POSTGRESQL:
            try:
                import psycopg2
                conn = psycopg2.connect(config.DATABASE_URL)
                cur = conn.cursor()
                cur.execute(
                    """INSERT INTO documents (document_id, document_name, document_type, file_path, chunk_count, status)
                       VALUES (%s, %s, %s, %s, %s, 'ready')
                       ON CONFLICT (document_id) DO UPDATE SET chunk_count = EXCLUDED.chunk_count, status = 'ready'""",
                    (doc_id, doc_id.replace("_", " ").title(), doc_type, str(path), len(chunks))
                )
                conn.commit()
                conn.close()
            except Exception as e:
                logger.warning(f"Failed to store document metadata in PostgreSQL: {e}")

        _store_job_status(rds, doc_id, STATUS_READY, {"chunks": len(chunks)})
        logger.info(f"Document {doc_id} ready: {len(chunks)} chunks")

    except Exception as e:
        logger.exception(f"Document ingestion failed: {doc_id}")
        _store_job_status(rds, doc_id, STATUS_FAILED, {"error": str(e)[:500]})


def process_data_job(job: dict, rds):
    """Process a data ingestion job: parse → profile → validate → store."""
    dataset_id = job.get("dataset_id")
    file_path = job.get("file_path")

    logger.info(f"Processing dataset: {dataset_id} ({file_path})")

    try:
        _store_job_status(rds, dataset_id, STATUS_PROCESSING)

        from src.analytics.data_hub import ingest_file
        with open(file_path, "rb") as f:
            result = ingest_file(f.read(), Path(file_path).name)

        _store_job_status(rds, dataset_id, STATUS_READY, {"result": json.dumps(result, default=str)[:2000]})
        logger.info(f"Dataset {dataset_id} ready: {result.get('total_rows', 0)} rows")

    except Exception as e:
        logger.exception(f"Data ingestion failed: {dataset_id}")
        _store_job_status(rds, dataset_id, STATUS_FAILED, {"error": str(e)[:500]})


def main():
    logger.info("Worker started. Listening for jobs...")
    logger.info(f"  DATABASE_URL configured: {bool(config.DATABASE_URL)}")
    logger.info(f"  REDIS_URL: {REDIS_URL}")

    rds = get_redis()

    # Verify Redis connection
    try:
        rds.ping()
        logger.info("Redis connection: OK")
    except redis.ConnectionError:
        logger.error("Cannot connect to Redis. Retrying...")
        time.sleep(5)

    while True:
        try:
            # Block-pop from queues with 5s timeout
            result = rds.brpop([QUEUE_DOCUMENT, QUEUE_DATA], timeout=5)
            if result is None:
                continue

            queue_name, job_json = result
            job = json.loads(job_json)

            if queue_name == QUEUE_DOCUMENT:
                process_document_job(job, rds)
            elif queue_name == QUEUE_DATA:
                process_data_job(job, rds)

        except redis.ConnectionError:
            logger.warning("Redis connection lost, retrying in 5s...")
            time.sleep(5)
        except Exception as e:
            logger.exception(f"Worker error: {e}")
            time.sleep(1)


if __name__ == "__main__":
    main()
