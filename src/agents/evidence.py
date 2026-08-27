"""
Evidence model — typed data structures for all evidence the system collects.

Every claim in the final response must be traceable to an Evidence object.
This enables provenance, verification, citations, debugging, and auditability.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Evidence:
    """A single piece of evidence supporting a claim."""
    evidence_id: str = field(default_factory=lambda: f"ev_{uuid.uuid4().hex[:12]}")
    evidence_type: str = "unknown"          # "structured" | "unstructured" | "derived"
    source: str = ""                        # asset name / document name
    asset_id: Optional[str] = None
    metric: Optional[str] = None            # business concept resolved
    query: Optional[str] = None             # SQL or retrieval query
    result: Any = None                      # raw result data
    confidence: float = 1.0                 # 0.0–1.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    # For unstructured evidence
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    page: Optional[int] = None
    section: Optional[str] = None
    text: Optional[str] = None
    relevance_score: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "type": self.evidence_type,
            "source": self.source,
            "asset_id": self.asset_id,
            "metric": self.metric,
            "query": self.query,
            "result": self.result,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "page": self.page,
            "section": self.section,
            "text": self.text,
            "relevance_score": self.relevance_score,
        }


@dataclass
class StructuredEvidence(Evidence):
    """Evidence from SQL queries against workspace data."""
    evidence_type: str = "structured"
    sql_query: Optional[str] = None
    rows_affected: int = 0
    columns: List[str] = field(default_factory=list)


@dataclass
class DocumentEvidence(Evidence):
    """Evidence from RAG document retrieval."""
    evidence_type: str = "unstructured"
    document_name: str = ""
    document_type: str = ""
    chunk_text: str = ""
    relevance_score: float = 0.0


@dataclass
class DerivedEvidence(Evidence):
    """Evidence derived from computation over other evidence."""
    evidence_type: str = "derived"
    source_evidence_ids: List[str] = field(default_factory=list)


class EvidenceGraph:
    """Tracks all evidence collected during an execution and supports provenance queries."""

    def __init__(self):
        self._evidence: Dict[str, Evidence] = {}
        self._claims: List[Dict[str, Any]] = []  # claim -> evidence links

    def add(self, evidence: Evidence) -> str:
        self._evidence[evidence.evidence_id] = evidence
        return evidence.evidence_id

    def get(self, evidence_id: str) -> Optional[Evidence]:
        return self._evidence.get(evidence_id)

    def link_claim(self, claim: str, evidence_ids: List[str], confidence: float = 1.0):
        self._claims.append({
            "claim": claim,
            "evidence_ids": evidence_ids,
            "confidence": confidence,
        })

    def all_evidence(self) -> List[Evidence]:
        return list(self._evidence.values())

    def structured_evidence(self) -> List[StructuredEvidence]:
        return [e for e in self._evidence.values() if isinstance(e, StructuredEvidence)]

    def document_evidence(self) -> List[DocumentEvidence]:
        return [e for e in self._evidence.values() if isinstance(e, DocumentEvidence)]

    def to_dict(self) -> dict:
        return {
            "evidence": [e.to_dict() for e in self._evidence.values()],
            "claims": self._claims,
            "total_evidence": len(self._evidence),
        }
