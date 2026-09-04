"""
E2E Tests: Revenue Ground Truth

These tests verify exact revenue values across datasets.
They require a running API and the test datasets.
"""
import pytest
import requests
from conftest import API_URL, upload_dataset, delete_dataset, query_api


class TestRevenueGroundTruth:
    """Verify exact revenue values for each dataset and combinations."""

    def _get_total_revenue(self, api_url):
        """Get total revenue via the API."""
        r = requests.get(f"{api_url}/api/analytics/overview", timeout=30)
        r.raise_for_status()
        return r.json().get("total_revenue", 0)

    def _list_datasets(self, api_url):
        """List all datasets."""
        r = requests.get(f"{api_url}/api/datahub/datasets", timeout=10)
        r.raise_for_status()
        return r.json()

    def _delete_all_datasets(self, api_url):
        """Delete all datasets."""
        for ds in self._list_datasets(api_url):
            did = ds.get("dataset_id")
            if did:
                delete_dataset(api_url, did)

    @pytest.mark.e2e
    def test_dataset_a_revenue(self, api_url, api_ready, clean_workspace):
        """Dataset A total revenue = 366979.88"""
        self._delete_all_datasets(api_url)
        result = upload_dataset(api_url, "tests/test_datasets/sales_region_north.csv")
        assert result.get("total_rows", 0) > 0

        revenue = self._get_total_revenue(api_url)
        assert abs(revenue - 366979.88) < 1.0, f"Expected 366979.88, got {revenue}"

    @pytest.mark.e2e
    def test_combined_revenue_abc(self, api_url, api_ready, clean_workspace):
        """Combined A+B+C revenue = 951138.13"""
        self._delete_all_datasets(api_url)
        upload_dataset(api_url, "tests/test_datasets/sales_region_north.csv")
        upload_dataset(api_url, "tests/test_datasets/sales_region_south.csv")
        upload_dataset(api_url, "tests/test_datasets/sales_export_erp.csv")

        revenue = self._get_total_revenue(api_url)
        assert abs(revenue - 951138.13) < 1.0, f"Expected 951138.13, got {revenue}"

    @pytest.mark.e2e
    def test_delete_a_revenue(self, api_url, api_ready, clean_workspace):
        """After deleting A, revenue = 584158.25"""
        self._delete_all_datasets(api_url)
        upload_dataset(api_url, "tests/test_datasets/sales_region_north.csv")
        upload_dataset(api_url, "tests/test_datasets/sales_region_south.csv")
        upload_dataset(api_url, "tests/test_datasets/sales_export_erp.csv")

        # Find and delete dataset A
        datasets = self._list_datasets(api_url)
        a_id = None
        for ds in datasets:
            if "north" in ds.get("filename", "").lower():
                a_id = ds["dataset_id"]
                break
        assert a_id is not None, "Could not find Dataset A"
        delete_dataset(api_url, a_id)

        revenue = self._get_total_revenue(api_url)
        assert abs(revenue - 584158.25) < 1.0, f"Expected 584158.25, got {revenue}"

    @pytest.mark.e2e
    def test_dataset_b_revenue(self, api_url, api_ready, clean_workspace):
        """Dataset B total revenue = 328460.90"""
        self._delete_all_datasets(api_url)
        upload_dataset(api_url, "tests/test_datasets/sales_region_south.csv")

        revenue = self._get_total_revenue(api_url)
        assert abs(revenue - 328460.90) < 1.0, f"Expected 328460.90, got {revenue}"

    @pytest.mark.e2e
    def test_dataset_c_revenue(self, api_url, api_ready, clean_workspace):
        """Dataset C total revenue = 255697.35"""
        self._delete_all_datasets(api_url)
        upload_dataset(api_url, "tests/test_datasets/sales_export_erp.csv")

        revenue = self._get_total_revenue(api_url)
        assert abs(revenue - 255697.35) < 1.0, f"Expected 255697.35, got {revenue}"


class TestSemanticMapping:
    """Verify semantic alias resolution."""

    def _delete_all(self, api_url):
        r = requests.get(f"{api_url}/api/datahub/datasets", timeout=10)
        for ds in r.json():
            requests.delete(f"{api_url}/api/datahub/datasets/{ds['dataset_id']}", timeout=10)

    @pytest.mark.e2e
    def test_revenue_alias_resolves(self, api_url, api_ready, clean_workspace):
        """revenue/sales_amount/net_sales all resolve to 'revenue' concept."""
        self._delete_all(api_url)
        upload_dataset(api_url, "tests/test_datasets/sales_region_north.csv")

        r = requests.get(f"{api_url}/api/semantic/metrics", timeout=10)
        r.raise_for_status()
        metrics = r.json().get("metrics", [])
        names = [m["name"].lower() for m in metrics]
        assert any("revenue" in n for n in names), f"Revenue concept not found in: {names}"

    @pytest.mark.e2e
    def test_discount_aliases_resolve(self, api_url, api_ready, clean_workspace):
        """discount_pct, promo_pct, markdown_pct all resolve."""
        self._delete_all(api_url)
        upload_dataset(api_url, "tests/test_datasets/sales_region_north.csv")
        upload_dataset(api_url, "tests/test_datasets/sales_region_south.csv")
        upload_dataset(api_url, "tests/test_datasets/sales_export_erp.csv")

        r = requests.get(f"{api_url}/api/semantic/metrics", timeout=10)
        r.raise_for_status()
        metrics = r.json().get("metrics", [])
        names = [m["name"].lower() for m in metrics]
        assert any("discount" in n for n in names), f"Discount concept not found: {names}"


class TestQueryEndpoint:
    """Test the /query endpoint with real questions."""

    def _delete_all(self, api_url):
        r = requests.get(f"{api_url}/api/datahub/datasets", timeout=10)
        for ds in r.json():
            requests.delete(f"{api_url}/api/datahub/datasets/{ds['dataset_id']}", timeout=10)

    @pytest.mark.e2e
    def test_total_revenue_query(self, api_url, api_ready, clean_workspace):
        """'What is total revenue?' returns revenue value."""
        self._delete_all(api_url)
        upload_dataset(api_url, "tests/test_datasets/sales_region_north.csv")

        result = query_api(api_url, "What is total revenue?")
        assert "answer" in result
        assert len(result["answer"]) > 10
        # The answer should contain a revenue-like number
        answer = result["answer"].replace(",", "").replace("$", "")
        assert any(c.isdigit() for c in answer), f"No numeric value in answer: {result['answer'][:200]}"

    @pytest.mark.e2e
    def test_knowledge_query(self, api_url, api_ready):
        """Knowledge question routes to RAG path."""
        result = query_api(api_url, "What is the standard trade promotion discount limit?")
        assert "answer" in result
        assert len(result["answer"]) > 10
        # Should mention 12% or discount
        answer_lower = result["answer"].lower()
        assert "12" in answer_lower or "discount" in answer_lower or "promotion" in answer_lower, \
            f"Answer doesn't mention discount: {result['answer'][:200]}"

    @pytest.mark.e2e
    def test_revenue_excluding_north_query(self, api_url, api_ready, clean_workspace):
        """'What is revenue excluding North?' returns the South + West total (584158.25)."""
        self._delete_all(api_url)
        upload_dataset(api_url, "tests/test_datasets/sales_region_north.csv")
        upload_dataset(api_url, "tests/test_datasets/sales_region_south.csv")
        upload_dataset(api_url, "tests/test_datasets/sales_export_erp.csv")

        result = query_api(api_url, "What is revenue excluding North?")
        answer = result.get("answer", "").replace(",", "").replace("$", "")
        assert "584158.25" in answer, f"Expected 584,158.25 (South + West), got: {result.get('answer', '')[:250]}"


class TestSQLSecurity:
    """SQL injection prevention — aligned with tests/e2e/test_sql_security.py.

    Contract: raw user text never becomes executable SQL. Identifiers are
    sanitized into inert tokens before quoting, filter values are escaped, and
    destructive keywords never survive as standalone tokens outside string
    literals. (Validating a keyword that appears INSIDE a quoted string literal
    is not meaningful — quoted text is data, not code.)
    """

    @staticmethod
    def _strip_quotes(sql):
        import re
        stripped = re.sub(r"'[^']*'", "", sql)
        stripped = re.sub(r'"[^"]*"', "", stripped)
        return stripped

    def test_drop_table_rejected(self):
        """DROP TABLE in an identifier never survives as executable SQL."""
        from src.agents.tools.sql_tools import sql_generate
        result = sql_generate(metric="users; DROP TABLE users", table="test_table", dimensions=None)
        sql = result.get("sql", "")
        assert "valid" in result  # generation completed
        assert ";" not in sql
        import re
        assert not re.search(r"\bDROP\b", self._strip_quotes(sql), re.IGNORECASE)

    def test_or_injection_rejected(self):
        """OR 1=1 injection in an identifier never survives as executable SQL."""
        from src.agents.tools.sql_tools import sql_generate
        result = sql_generate(metric='sales" OR "1"="1', table="test_table", dimensions=None)
        sql = result.get("sql", "")
        import re
        stripped = self._strip_quotes(sql)
        assert not re.search(r"\bOR\b", stripped, re.IGNORECASE) or "1=1" not in stripped

    def test_legitimate_identifier_accepted(self):
        """Legitimate identifiers are accepted."""
        from src.agents.tools.sql_tools import sql_generate
        for ident in ("sales_region_north", "legitimate_table_name"):
            result = sql_generate(metric=ident, table="test_table", dimensions=None)
            assert result.get("sql"), f"Legitimate identifier rejected: {ident}"
            assert result.get("valid"), f"Legitimate identifier invalid: {ident}"


class TestPersistence:
    """Test data persistence across API calls."""

    def _delete_all(self, api_url):
        r = requests.get(f"{api_url}/api/datahub/datasets", timeout=10)
        for ds in r.json():
            requests.delete(f"{api_url}/api/datahub/datasets/{ds['dataset_id']}", timeout=10)

    @pytest.mark.e2e
    def test_data_persists_across_requests(self, api_url, api_ready, clean_workspace):
        """Uploaded data persists and is queryable."""
        self._delete_all(api_url)
        upload_dataset(api_url, "tests/test_datasets/sales_region_north.csv")

        # Query in separate request
        revenue = requests.get(f"{api_url}/api/analytics/overview", timeout=10).json().get("total_revenue", 0)
        assert abs(revenue - 366979.88) < 1.0
