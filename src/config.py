"""
Central configuration for the Sales & Marketing Intelligence Platform.

All tunables (paths, model choice, retrieval knobs) live here so behavior
can be changed via .env without touching code.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Storage ---
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "warehouse.db"))
KB_DIR = Path(os.getenv("KB_DIR", DATA_DIR / "knowledge_base"))
VECTOR_STORE_PATH = Path(os.getenv("VECTOR_STORE_PATH", DATA_DIR / "vector_store.pkl"))
DOCUMENTS_DIR = Path(os.getenv("DOCUMENTS_DIR", DATA_DIR / "documents"))

# --- Database ---
DATABASE_URL = os.getenv("DATABASE_URL", "")
# Normalize URL: postgresql+asyncpg:// → postgresql://
if DATABASE_URL and "+asyncpg" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
USE_POSTGRESQL = bool(DATABASE_URL and DATABASE_URL.startswith("postgresql"))

# --- Redis ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# --- Synthetic data volume ---
N_PRODUCTS = int(os.getenv("N_PRODUCTS", 120))
N_SALES = int(os.getenv("N_SALES", 6000))
N_CAMPAIGNS = int(os.getenv("N_CAMPAIGNS", 24))
N_REVIEWS = int(os.getenv("N_REVIEWS", 1200))
N_CUSTOMERS = int(os.getenv("N_CUSTOMERS", 600))
RANDOM_SEED = int(os.getenv("RANDOM_SEED", 42))

# --- Chunking ---
CHUNK_SIZE_WORDS = int(os.getenv("CHUNK_SIZE_WORDS", 180))
CHUNK_OVERLAP_WORDS = int(os.getenv("CHUNK_OVERLAP_WORDS", 40))

# --- Retrieval ---
TOP_K_VECTOR = int(os.getenv("TOP_K_VECTOR", 8))
TOP_K_KEYWORD = int(os.getenv("TOP_K_KEYWORD", 8))
TOP_K_FINAL = int(os.getenv("TOP_K_FINAL", 4))
VECTOR_WEIGHT = float(os.getenv("VECTOR_WEIGHT", 0.6))
KEYWORD_WEIGHT = float(os.getenv("KEYWORD_WEIGHT", 0.4))
MIN_RELEVANCE_SCORE = float(os.getenv("MIN_RELEVANCE_SCORE", 0.08))

# --- Embeddings ---
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "tfidf")  # "tfidf" | "neural"
NEURAL_EMBEDDING_MODEL = os.getenv("NEURAL_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

# --- LLM ---
LLM_BACKEND = os.getenv("LLM_BACKEND", "fallback")  # "ollama" | "fallback"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", 60))

# --- API ---
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 8000))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")

# --- Security ---
MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", 50 * 1024 * 1024))  # 50MB

DATA_DIR.mkdir(parents=True, exist_ok=True)
KB_DIR.mkdir(parents=True, exist_ok=True)
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
