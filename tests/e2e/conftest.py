"""
E2E Test Configuration

These tests require a running QueryBridge instance:
  docker compose up -d
  
Then run:
  pytest tests/e2e/ -v

Environment variables:
  API_URL: Base URL for the API (default: http://localhost:8000)
"""
import os
import time
import pytest
import requests

API_URL = os.getenv("API_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def api_url():
    """Base API URL."""
    return API_URL


@pytest.fixture(scope="session")
def api_ready(api_url):
    """Wait for API to be ready."""
    for i in range(30):
        try:
            r = requests.get(f"{api_url}/health", timeout=5)
            if r.status_code == 200:
                return True
        except requests.ConnectionError:
            pass
        time.sleep(2)
    pytest.skip("API not available")


@pytest.fixture(scope="session")
def clean_workspace(api_url, api_ready):
    """Clean workspace before tests."""
    try:
        r = requests.get(f"{api_url}/api/datahub/datasets", timeout=10)
        if r.status_code == 200:
            for ds in r.json():
                did = ds.get("dataset_id")
                if did:
                    requests.delete(f"{api_url}/api/datahub/datasets/{did}", timeout=10)
    except Exception:
        pass
    return True


@pytest.fixture
def dataset_a_path():
    """Path to Dataset A."""
    return os.path.join(os.path.dirname(__file__), "..", "test_datasets", "sales_region_north.csv")


@pytest.fixture
def dataset_b_path():
    """Path to Dataset B."""
    return os.path.join(os.path.dirname(__file__), "..", "test_datasets", "sales_region_south.csv")


@pytest.fixture
def dataset_c_path():
    """Path to Dataset C."""
    return os.path.join(os.path.dirname(__file__), "..", "test_datasets", "sales_export_erp.csv")


def upload_dataset(api_url, filepath):
    """Upload a CSV file to the data hub."""
    filename = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        files = {"file": (filename, f, "text/csv")}
        r = requests.post(f"{api_url}/api/datahub/upload", files=files, timeout=30)
    r.raise_for_status()
    return r.json()


def delete_dataset(api_url, dataset_id):
    """Delete a dataset by ID."""
    r = requests.delete(f"{api_url}/api/datahub/datasets/{dataset_id}", timeout=10)
    return r.status_code == 200


def query_api(api_url, question, timeout=60):
    """Send a query to the /query endpoint."""
    r = requests.post(f"{api_url}/query", json={"question": question}, timeout=timeout)
    r.raise_for_status()
    return r.json()
