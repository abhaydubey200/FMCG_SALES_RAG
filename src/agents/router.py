"""
Fast Router — deterministic query classification with zero LLM overhead.

Replaces the 3-stage LLM pipeline (Intent → Planning → Analytics → Synthesis)
with a single deterministic router that classifies queries instantly.

Route types:
  ANALYTICS  — pure numerical/data queries (revenue, sales, trends)
  KNOWLEDGE  — document/policy questions (rules, limits, guidelines)
  HYBRID     — both data and documents needed
  COMPLEX    — multi-step reasoning (investigations, root cause)
  AMBIGUOUS  — unclear intent, needs clarification
  UNSUPPORTED — out of scope (predictions, opinions, etc.)

The router NEVER makes LLM calls. It uses:
  1. Pattern matching (regex-like keyword rules)
  2. Structural analysis (question structure, entity extraction)
  3. Semantic hints (alias resolution via the Semantic Layer)

This module is the FIRST step in the pipeline — everything after it
uses deterministic tools until the final ONE LLM synthesis call.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("agents.router")


@dataclass
class RouteResult:
    """Deterministic routing decision."""
    route: str  # ANALYTICS | KNOWLEDGE | HYBRID | COMPLEX | AMBIGUOUS | UNSUPPORTED
    confidence: float
    reasoning: str
    entities: List[str] = field(default_factory=list)
    metrics: List[str] = field(default_factory=list)
    dimensions: List[str] = field(default_factory=list)
    needs_llm: bool = False  # True only for COMPLEX/AMBIGUOUS
    causal: bool = False  # True when the query asks WHY/what caused (causal analysis)


# ──────────────────────────────────────────────────────────────────────
# Pattern definitions
# ──────────────────────────────────────────────────────────────────────

# Knowledge-focused patterns (document/policy terms)
_KNOWLEDGE_PATTERNS = [
    (r"\bpolic(y|ies)\b", "policy/policies"),
    (r"\brul(e|es)\b", "rules"),
    (r"\blimit(s|ed)?\b", "limits"),
    (r"\bguideline(s)?\b", "guidelines"),
    (r"\bstandard(s)?\b", "standards"),
    (r"\bcompliance\b", "compliance"),
    (r"\bregulation(s)?\b", "regulations"),
    (r"\btarget(s)?\b", "targets"),
    (r"\bpractices?\b", "practices"),
    (r"\bprocedure(s)?\b", "procedures"),
    (r"\bframework\b", "framework"),
    (r"\bcode of conduct\b", "code of conduct"),
    (r"\btrade promotion(s)?\b", "trade promotion"),
    (r"\bcategory role\b", "category role"),
    (r"\bdiscount limit\b", "discount limit"),
    (r"\brecyclability\b", "recyclability"),
    (r"\bpackaging\b", "packaging"),
    (r"\binvestment split\b", "investment split"),
    (r"\bmarketing investment\b", "marketing investment"),
    (r"\bsustainability\b", "sustainability"),
    (r"\brecall\b", "recall"),
    (r"\bpricing\b", "pricing"),
    (r"\bstrategy\b", "strategy"),
    (r"\baccording to\b", "according to"),
    (r"\bwhat does .+ (say|state|specify)\b", "document reference"),
    (r"\bwhat is the (policy|rule|limit|guideline|standard)\b", "policy question"),
    (r"\bwhat are the (policies|rules|limits|guidelines|standards)\b", "policy question"),
]

# Analytics patterns (data/numerical terms)
_ANALYTICS_PATTERNS = [
    (r"\btotal\b", "total"),
    (r"\bsum\b", "sum"),
    (r"\baverage\b", "average"),
    (r"\bmax(imum)?\b", "maximum"),
    (r"\bmin(imum)?\b", "minimum"),
    (r"\bcount\b", "count"),
    (r"\brevenue\b", "revenue"),
    (r"\bsales\b", "sales"),
    (r"\bunits?\b", "units"),
    (r"\bquantity\b", "quantity"),
    (r"\bmargin(s)?\b", "margin"),
    (r"\bprofit(s)?\b", "profit"),
    (r"\bspend\b", "spend"),
    (r"\bdiscount(s|ed)?\b", "discount"),
    (r"\btrend(s|ing)?\b", "trend"),
    (r"\bcompare(d|ison)?\b", "comparison"),
    (r"\bperformance\b", "performance"),
    (r"\bby (region|category|product|month|quarter|year|segment|channel)\b", "dimensional"),
    (r"\btop \d+\b", "ranking"),
    (r"\bhow (much|many|many)\b", "quantitative"),
    (r"\bbreakdown\b", "breakdown"),
    (r"\bgrowth\b", "growth"),
    (r"\bdecline(d)?\b", "decline"),
    (r"\bshow\b", "show"),
    (r"\bwhat is (the )?total\b", "total question"),
]

# Investigation patterns (root cause / diagnostic).
# Causal phrasing must WIN over analytics patterns: a question like
# "What caused the revenue decline in the West market?" contains revenue +
# decline (analytics terms) AND causal terms. Causal terms are the stronger
# intent signal — the query is about WHY, not about the number itself.
# Each match adds 1.6 to COMPLEX (analytics terms add 1.0 each), so a single
# causal phrase outranks a two-term analytics phrase.
_INVESTIGATION_PATTERNS = [
    (r"\bwhy (did|does|is|was|were|has|have)\b", "causal question"),
    (r"\bwhy is .+ (declining|decreasing|dropping|falling|increasing|rising|growing)\b", "change investigation"),
    (r"\bwhat caused\b", "causal question"),
    (r"\bcaused\b", "causal question"),
    (r"\bcause of\b", "causal question"),
    (r"\bcauses?\b", "causal question"),
    (r"\bcaused by\b", "causal question"),
    (r"\bwhat (drove|drives)\b", "causal question"),
    (r"\bwhat is driving\b", "causal question"),
    (r"\bwhat['’]s driving\b", "causal question"),
    (r"\bdriver[s]? of\b", "causal question"),
    (r"\broot cause\b", "root cause"),
    (r"\breason for\b", "reason question"),
    (r"\breason behind\b", "reason question"),
    (r"\bwhat explains\b", "causal question"),
    (r"\bwhich factors\b", "causal question"),
    (r"\bexplain the (decline|decrease|drop|fall|increase|rise|growth|change)\b", "change explanation"),
    (r"\bexplain(ation)?\b", "explanation"),
    (r"\binvestigate\b", "investigation"),
    (r"\bwhy (is|are) .+ (performing|doing) (better|worse)\b", "comparison investigation"),
]

# Ambiguous patterns
_AMBIGUOUS_PATTERNS = [
    (r"\bhow is .+ doing\b", "vague performance"),
    (r"\btell me about\b", "open-ended"),
 (r"\bwhat about\b", "open-ended"),
    (r"\bhow's it going\b", "casual"),
    (r"\bstatus\b", "status request"),
]

# Unsupported patterns
_UNSUPPORTED_PATTERNS = [
    (r"\b(predict|forecast|will be in 20\d\d)\b", "prediction"),
    (r"\b(?:will|going to|be).{0,30}?(?:in|by)\s+20(?:2[5-9]|3\d)\b", "future projection"),
    (r"\bopinion\b", "opinion"),
    (r"\brecommend(ation)?\b", "recommendation"),
    (r"\bshould we\b", "advisory"),
    (r"\bwhat if\b", "hypothetical"),
]


def _match_patterns(text: str, patterns: List[Tuple[str, str]]) -> List[str]:
    """Return list of matched pattern labels."""
    matches = []
    for regex, label in patterns:
        if re.search(regex, text, re.IGNORECASE):
            matches.append(label)
    return matches


def _extract_entities(text: str) -> List[str]:
    """Extract potential entity names from the query."""
    entities = []
    # Look for quoted strings
    entities.extend(re.findall(r'"([^"]+)"', text))
    entities.extend(re.findall(r"'([^']+)'", text))
    # Look for capitalized words (potential entity names)
    words = text.split()
    for w in words:
        if w[0].isupper() and len(w) > 2 and w.lower() not in {
            "what", "how", "why", "show", "tell", "compare", "total",
            "revenue", "sales", "the", "and", "for", "with", "from",
            "are", "were", "was", "does", "did", "will", "can",
        }:
            entities.append(w)
    return entities


def _extract_metrics(text: str) -> List[str]:
    """Extract metric names from the query."""
    metrics = []
    metric_map = {
        "revenue": ["revenue", "sales", "income", "turnover", "net sales"],
        "quantity": ["units", "quantity", "volume", "count"],
        "spend": ["spend", "marketing spend", "ad spend", "advertising"],
        "margin": ["margin", "gross margin", "profit margin"],
        "profit": ["profit", "gross profit", "net profit"],
        "discount": ["discount", "discount rate", "markdown"],
        "roas": ["roas", "return on ad spend"],
    }
    text_lower = text.lower()
    for metric_name, aliases in metric_map.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", text_lower) for alias in aliases):
            metrics.append(metric_name)
    return metrics


def _extract_dimensions(text: str) -> List[str]:
    """Extract dimension names from the query."""
    dimensions = []
    dim_patterns = [
        (r"\bby (region|territory|market)\b", "region"),
        (r"\bby (category|categories)\b", "category"),
        (r"\bby product(s)?\b", "product"),
        (r"\bby month(ly)?\b", "month"),
        (r"\bby quarter(ly)?\b", "quarter"),
        (r"\bby year(ly)?\b", "year"),
        (r"\bby segment\b", "segment"),
        (r"\bby channel\b", "channel"),
        (r"\bby customer\b", "customer"),
    ]
    for pattern, dim in dim_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            dimensions.append(dim)
    return dimensions


class FastRouter:
    """
    Deterministic query router — zero LLM overhead.
    
    Architecture:
        Question → Pattern Analysis → Route Decision → Execution Path
    
    This replaces the old 3-LLM-call pipeline with instant routing.
    """

    def route(self, query: str, conversation_context: List[Dict] = None) -> RouteResult:
        """
        Route a query to the appropriate execution path.
        
        Returns a RouteResult with:
          - route: ANALYTICS | KNOWLEDGE | HYBRID | COMPLEX | AMBIGUOUS | UNSUPPORTED
          - confidence: 0.0-1.0
          - reasoning: explanation
          - entities, metrics, dimensions: extracted from query
          - needs_llm: True only for COMPLEX/AMBIGUOUS
        """
        t0 = __import__("time").time()
        text = query.lower().strip()

        # ── Phase 1: Pattern matching ──
        knowledge_matches = _match_patterns(text, _KNOWLEDGE_PATTERNS)
        analytics_matches = _match_patterns(text, _ANALYTICS_PATTERNS)
        investigation_matches = _match_patterns(text, _INVESTIGATION_PATTERNS)
        ambiguous_matches = _match_patterns(text, _AMBIGUOUS_PATTERNS)
        unsupported_matches = _match_patterns(text, _UNSUPPORTED_PATTERNS)

        # ── Phase 2: Score each route ──
        # COMPLEX weight 2.0: a single causal phrase beats a 2-term analytics
        # phrase ("revenue" + "decline" = 2.0), so causal intent never loses
        # to ordinary retrieval on a tie. Route selection below also prefers
        # COMPLEX on exact ties when investigation terms are present.
        scores = {
            "ANALYTICS": len(analytics_matches) * 1.0,
            "KNOWLEDGE": len(knowledge_matches) * 1.5,  # Knowledge terms are strong signals
            "HYBRID": 0.0,
            "COMPLEX": len(investigation_matches) * 2.0,
            "AMBIGUOUS": len(ambiguous_matches) * 2.0,  # Strong signal for ambiguity
            "UNSUPPORTED": len(unsupported_matches) * 2.0,  # Strong signal for unsupported
        }

        # Hybrid: knowledge terms AND a STRONG analytical intent (data + documents needed)
        # Soft words like 'discount'/'limit' alone do not trigger hybrid — a policy
        # question about discount limits must stay KNOWLEDGE.
        if knowledge_matches and analytics_matches:
            _strong_analytics = {"revenue", "sales", "units", "quantity", "margin",
                                 "profit", "spend", "total", "trend", "comparison",
                                 "breakdown", "growth", "dimensional", "ranking",
                                 "average", "sum", "maximum", "minimum", "count",
                                 "quantitative", "show", "decline"}
            if any(l in _strong_analytics for l in analytics_matches):
                scores["HYBRID"] = (len(knowledge_matches) + len(analytics_matches)) * 1.3

        # ── Phase 3: Entity/metric/dimension extraction ──
        entities = _extract_entities(query)
        metrics = _extract_metrics(query)
        dimensions = _extract_dimensions(query)

        # ── Phase 4: Route selection ──
        route = max(scores, key=scores.get)
        max_score = scores[route]

        # Causal tie-break: when investigation terms are present and COMPLEX
        # ties (or beats) the winner, causal analysis wins — a "why" question
        # must never degrade into plain number retrieval.
        if investigation_matches and scores["COMPLEX"] >= max_score:
            route = "COMPLEX"
            max_score = scores["COMPLEX"]

        # Causal flag: any causal/investigation phrasing → the query asks WHY.
        causal = bool(investigation_matches)

        # Handle ties and low confidence
        if max_score == 0:
            # No strong signals — never invent an analytics answer for text we
            # can't classify (greetings, injection attempts, random phrases).
            route = "AMBIGUOUS"
            max_score = 0.1
            reasoning = "No clear analytics, knowledge, or investigation signal — ambiguous"
        elif route == "AMBIGUOUS" and max_score >= 2.0:
            reasoning = f"Ambiguous patterns matched: {', '.join(ambiguous_matches)}"
        elif route == "UNSUPPORTED" and max_score >= 2.0:
            reasoning = f"Unsupported query type: {', '.join(unsupported_matches)}"
        elif route == "HYBRID":
            reasoning = f"Both data ({', '.join(analytics_matches[:2])}) and document ({', '.join(knowledge_matches[:2])}) terms present"
        elif route == "KNOWLEDGE":
            reasoning = f"Document/policy terms: {', '.join(knowledge_matches[:3])}"
        elif route == "COMPLEX":
            reasoning = f"Investigation terms: {', '.join(investigation_matches[:3])}"
        else:
            reasoning = f"Data terms: {', '.join(analytics_matches[:3])}"

        confidence = min(1.0, max_score / 3.0)

        # ── Phase 5: Determine if LLM synthesis is potentially needed ──
        # Only genuinely complex investigations may consume ONE synthesis call.
        # AMBIGUOUS/UNSUPPORTED queries are answered deterministically (refusals).
        needs_llm = route == "COMPLEX"

        elapsed_ms = round((__import__("time").time() - t0) * 1000, 2)
        logger.info(
            "Router: %s (confidence=%.2f, %.1fms) — %s",
            route, confidence, elapsed_ms, reasoning[:80],
        )

        return RouteResult(
            route=route,
            confidence=confidence,
            reasoning=reasoning,
            entities=entities,
            metrics=metrics,
            dimensions=dimensions,
            needs_llm=needs_llm,
            causal=causal,
        )


# ──────────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────────

_router: Optional[FastRouter] = None


def get_router() -> FastRouter:
    global _router
    if _router is None:
        _router = FastRouter()
    return _router
