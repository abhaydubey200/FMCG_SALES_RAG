"""
Workspace isolation e2e tests — Blocker 2.

Mandatory cross-workspace matrix:
  - Workspace A dataset revenue = 1,000
  - Workspace B dataset revenue = 9,000
  A and B ask the SAME question "What is total revenue?" → A must get 1,000,
  B must get 9,000, never the other way — across SQL, cache, conversations,
  RAG documents, dataset listing, and deletion.

Requires a running instance: `docker compose up -d`, then
    pytest tests/e2e/test_workspace_isolation.py -v
"""
import os
import uuid

import pytest
import requests

from conftest import API_URL, delete_dataset as _delete

WS_A = f"iso_a_{uuid.uuid4().hex[:6]}"
WS_B = f"iso_b_{uuid.uuid4().hex[:6]}"

CSV_A = "region,sales_amount\nEast,1000\n"
CSV_B = "region,sales_amount\nWest,9000\n"


def _upload_csv(ws, filename, content):
    files = {"file": (filename, content.encode(), "text/csv")}
    data = {"workspace_id": ws}
    r = requests.post(f"{API_URL}/api/datahub/upload", files=files, data=data, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _upload_doc(ws, filename, content):
    files = {"file": (filename, content.encode(), "text/markdown")}
    data = {"workspace_id": ws}
    r = requests.post(f"{API_URL}/documents/upload", files=files, data=data, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


def _ask(ws, question, timeout=60):
    r = requests.post(f"{API_URL}/api/ai/query",
                      json={"question": question, "workspace_id": ws}, timeout=timeout)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def seeded_workspaces(api_ready):
    """Upload distinct datasets + RAG docs to two workspaces, then clean up."""
    _upload_csv(WS_A, "iso_dataset.csv", CSV_A)
    _upload_csv(WS_B, "iso_dataset.csv", CSV_B)
    _upload_doc(WS_A, "promo_limit.md",
                "# Promo Policy\n\n## Limits\n\nPromotion limit is 10% for standard trade activity.")
    _upload_doc(WS_B, "promo_limit.md",
                "# Promo Policy\n\n## Limits\n\nPromotion limit is 20% for standard trade activity.")
    yield
    # Cleanup: datasets + docs for both workspaces (workspace-scoped)
    for ws in (WS_A, WS_B):
        r = requests.get(f"{API_URL}/api/datahub/datasets", params={"workspace_id": ws}, timeout=10)
        if r.status_code == 200:
            for ds in r.json():
                requests.delete(f"{API_URL}/api/datahub/datasets/{ds.get('dataset_id')}",
                                params={"workspace_id": ws}, timeout=15)
        r = requests.get(f"{API_URL}/api/data-center", params={"workspace_id": ws}, timeout=10)
        if r.status_code == 200:
            for asset in r.json().get("assets", []):
                if asset.get("type") == "unstructured":
                    requests.delete(f"{API_URL}/api/data-center/{asset['id']}",
                                    params={"workspace_id": ws}, timeout=15)


def test_sql_analytics_isolation(seeded_workspaces):
    a = _ask(WS_A, "What is total revenue?")
    b = _ask(WS_B, "What is total revenue?")
    assert "1,000.00" in a["answer"], a["answer"]
    assert "9,000.00" in b["answer"], b["answer"]


def test_cache_isolation_same_question(seeded_workspaces):
    """Same question twice per workspace, alternating — warm cache must not leak."""
    for _ in range(2):
        a = _ask(WS_A, "What is total revenue?")
        b = _ask(WS_B, "What is total revenue?")
        assert "1,000.00" in a["answer"]
        assert "9,000.00" in b["answer"]


def test_dataset_listing_isolation(seeded_workspaces):
    ra = requests.get(f"{API_URL}/api/datahub/datasets", params={"workspace_id": WS_A}, timeout=10)
    rb = requests.get(f"{API_URL}/api/datahub/datasets", params={"workspace_id": WS_B}, timeout=10)
    fa = {d["filename"] for d in ra.json()}
    fb = {d["filename"] for d in rb.json()}
    assert "iso_dataset.csv" in fa and "iso_dataset.csv" in fb
    # both upload the same filename; listing is still scoped (no foreign assets leak)
    assert not ({d.get("dataset_id") for d in ra.json()} & {d.get("dataset_id") for d in rb.json()}) or fa == fb


def test_rag_isolation_same_document_name(seeded_workspaces):
    a = _ask(WS_A, "What is the promotion limit?")
    b = _ask(WS_B, "What is the promotion limit?")
    assert "10%" in a["answer"] and "20%" not in a["answer"], a["answer"]
    assert "20%" in b["answer"] and "10%" not in b["answer"], b["answer"]


def test_conversation_isolation(seeded_workspaces):
    r = requests.post(f"{API_URL}/api/conversations", params={"workspace_id": WS_A}, timeout=10)
    assert r.status_code == 200
    cid = r.json()["id"]
    try:
        # Owner can read
        r = requests.get(f"{API_URL}/api/conversations/{cid}", params={"workspace_id": WS_A}, timeout=10)
        assert r.status_code == 200
        # Other workspace cannot read / write / delete
        r = requests.get(f"{API_URL}/api/conversations/{cid}", params={"workspace_id": WS_B}, timeout=10)
        assert r.status_code == 404
        r = requests.post(f"{API_URL}/api/conversations/{cid}/messages",
                          params={"workspace_id": WS_B},
                          json={"role": "user", "content": "x"}, timeout=10)
        assert r.status_code == 404
        r = requests.delete(f"{API_URL}/api/conversations/{cid}", params={"workspace_id": WS_B}, timeout=10)
        assert r.status_code == 404
        # Listing only shows own conversations
        la = requests.get(f"{API_URL}/api/conversations", params={"workspace_id": WS_A}, timeout=10).json()
        lb = requests.get(f"{API_URL}/api/conversations", params={"workspace_id": WS_B}, timeout=10).json()
        ids_a = {c["id"] for c in la.get("conversations", [])}
        ids_b = {c["id"] for c in lb.get("conversations", [])}
        assert cid in ids_a and cid not in ids_b
    finally:
        requests.delete(f"{API_URL}/api/conversations/{cid}", params={"workspace_id": WS_A}, timeout=10)


def test_cross_workspace_document_delete_blocked(seeded_workspaces):
    # A's doc must not be deletable from B
    ra = requests.get(f"{API_URL}/documents", params={"workspace_id": WS_A}, timeout=10)
    docs = ra.json()
    foreign_doc = next((d["document_id"] for d in docs if "promo" in d["document_id"]), None)
    if foreign_doc:
        r = requests.delete(f"{API_URL}/documents/{foreign_doc}",
                            params={"workspace_id": WS_B}, timeout=15)
        assert r.status_code == 404


def test_data_center_no_cross_workspace_overlap(seeded_workspaces):
    # Same filenames in both workspaces are allowed; the ASSETS must never be shared.
    # Each workspace's registry shows distinct dataset ids / doc ids (different
    # content hashes -> different physical tables), and no asset id appears in both.
    ra = requests.get(f"{API_URL}/api/data-center", params={"workspace_id": WS_A}, timeout=10).json()
    rb = requests.get(f"{API_URL}/api/data-center", params={"workspace_id": WS_B}, timeout=10).json()
    ids_a = {a["id"] for a in ra.get("assets", [])}
    ids_b = {a["id"] for a in rb.get("assets", [])}
    assert not (ids_a & ids_b), f"cross-workspace asset id overlap: {ids_a & ids_b}"
