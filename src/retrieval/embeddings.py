"""
Pluggable embedding interface.

Why pluggable: the assignment prefers neural embeddings (BGE/E5/Sentence
Transformers) but this sandbox has no network access to HuggingFace to
download model weights (see README "Environment Constraints"). Rather than
fake it, we implement a real, legitimate vector-space model — TF-IDF with
L2-normalized vectors and cosine similarity — behind the exact same
interface a neural embedder would use. Swapping in real neural embeddings
in an environment with HF access is a ~10-line change (see
NeuralEmbedder below) and nothing else in the retrieval/vector-store code
needs to change.
"""
from abc import ABC, abstractmethod
from typing import List

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from src import config


class BaseEmbedder(ABC):
    @abstractmethod
    def fit(self, corpus: List[str]) -> None:
        ...

    @abstractmethod
    def embed(self, texts: List[str]) -> np.ndarray:
        ...

    @property
    @abstractmethod
    def dim(self) -> int:
        ...


class TfidfEmbedder(BaseEmbedder):
    """
    A genuine vector-space embedding model. TF-IDF vectors are trained
    (fit) on the corpus of chunks, giving each chunk (and, at query time,
    each query) a dense-ish sparse vector in the same space. Cosine
    similarity over these vectors is mathematically the same operation
    used for neural embedding retrieval — only the vector *quality*
    differs (no semantic/synonym generalization), which we document as a
    known limitation in README "Limitations" and "Failure cases".
    """

    def __init__(self, max_features: int = 4096, ngram_range=(1, 2)):
        self.vectorizer = TfidfVectorizer(
            max_features=max_features,
            ngram_range=ngram_range,
            stop_words="english",
            sublinear_tf=True,
        )
        self._fitted = False

    def fit(self, corpus: List[str]) -> None:
        if not corpus:
            self._fitted = False
            return
        self.vectorizer.fit(corpus)
        self._fitted = True

    def embed(self, texts: List[str]) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("TfidfEmbedder.fit() must be called before embed().")
        vecs = self.vectorizer.transform(texts)
        vecs = normalize(vecs, norm="l2")
        return vecs.toarray().astype(np.float32)

    @property
    def dim(self) -> int:
        return len(self.vectorizer.vocabulary_) if self._fitted else 0


class NeuralEmbedder(BaseEmbedder):
    """
    Real neural embedder using sentence-transformers. Only usable in an
    environment with HuggingFace access (not this sandbox). Kept here so
    switching EMBEDDING_BACKEND=neural in .env is a drop-in change.
    """

    def __init__(self, model_name: str = None):
        from sentence_transformers import SentenceTransformer  # noqa: local import, optional dep
        self.model_name = model_name or config.NEURAL_EMBEDDING_MODEL
        self.model = SentenceTransformer(self.model_name)

    def fit(self, corpus: List[str]) -> None:
        # Neural embedders are pretrained; nothing to fit.
        return

    def embed(self, texts: List[str]) -> np.ndarray:
        vecs = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32)

    @property
    def dim(self) -> int:
        return self.model.get_sentence_embedding_dimension()


def get_embedder() -> BaseEmbedder:
    if config.EMBEDDING_BACKEND == "neural":
        return NeuralEmbedder()
    return TfidfEmbedder()
