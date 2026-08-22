"""
Prompt construction (documented for README "Prompt design" and
"Grounding strategy").

Design: every prompt has three parts:
  1. A system instruction enforcing grounding rules (never fabricate,
     separate fact/inference/unavailable, cite sources).
  2. A structured JSON "EVIDENCE" block — this is the single source of
     truth the LLM is allowed to draw from. Keeping evidence as JSON
     (not prose) makes it (a) unambiguous for the LLM to quote numbers
     from correctly, and (b) machine-parseable, which is what lets our
     fallback template generator (no LLM at all) produce a grounded
     answer from the *exact same evidence contract* a real LLM would
     receive. This is why swapping LLM_BACKEND doesn't require touching
     the RAG pipeline or retrieval code at all.
  3. The user's question, repeated last (recency helps instruction
     following in most models).
"""
import json

SYSTEM_INSTRUCTION = """You are a Sales & Marketing Intelligence Assistant for an e-commerce business.

Rules you MUST follow:
1. Only use facts contained in the EVIDENCE JSON block below. Never invent numbers, dates, campaign names, or policy statements that are not present in EVIDENCE.
2. Clearly separate: (a) facts available in the data, (b) information retrieved from documents, (c) calculated metrics, (d) your reasoning/inference connecting them, and (e) anything the evidence does not cover.
3. If EVIDENCE does not contain enough information to answer, say so explicitly rather than guessing. Do not answer questions about time periods or facts outside the provided evidence.
4. When EVIDENCE contains a conflict (e.g. two documents giving different numbers for the same thing), point out the conflict explicitly rather than silently picking one or averaging them.
5. Cite the source of every claim using the "source" fields present in EVIDENCE (document name + section, or "sales data" / "campaign data" / "review data" as applicable).
6. Be concise and structured. Prefer short paragraphs or bullet points over long prose."""


def build_prompt(question: str, query_type: str, evidence: dict) -> str:
    evidence_json = json.dumps(evidence, indent=2, default=str)
    return f"""EVIDENCE:
{evidence_json}

QUERY_TYPE: {query_type}

QUESTION: {question}

Answer the question using only the EVIDENCE above. Structure your answer with a direct answer first, then supporting evidence, then sources. If this is a diagnostic question, explicitly separate "Observed facts", "Possible explanations", and "Unsupported assumptions" (do not present the latter as fact)."""
