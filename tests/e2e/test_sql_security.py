"""
SQL Security Tests — verify injection prevention.
These tests can run without Docker (no database needed).
"""
import pytest
from src.agents.tools.sql_tools import sql_validate, sql_generate, _validate_sql


class TestSQLInjection:
    """Verify SQL injection is prevented in all identifier paths."""

    @pytest.mark.parametrize("malicious_input", [
        "users; DROP TABLE users",
        'sales" OR "1"="1',
        "revenue; DELETE FROM users",
        "foo); DROP TABLE assets;--",
        "sales--",
        "sales/*",
        "sales'",
        "sales OR 1=1",
        "admin'--",
        "' OR ''='",
        "1; SELECT * FROM users",
        "revenue\" AS x; DROP TABLE users; --",
    ])
    def test_malicious_identifier_rejected(self, malicious_input):
        """All malicious identifiers must be neutralized in generated SQL."""
        result = sql_generate(
            metric=malicious_input,
            table="test_table",
            dimensions=None,
        )
        sql = result.get("sql") or ""
        # Destructive keywords must never survive into executable SQL — either
        # the identifier is sanitized into a harmless token, or validation
        # rejects the statement outright.
        for kw in ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "CREATE"]:
            upper = sql.upper()
            stripped = re_sub_quotes(sql)
            assert not re_search(r"\b" + kw + r"\b", stripped), \
                f"Destructive SQL passed through ({kw}): {sql}"

    @pytest.mark.parametrize("legitimate_input", [
        "sales_region_north",
        "revenue",
        "order_date",
        "product_name",
        "discount_pct",
        "category",
    ])
    def test_legitimate_identifier_accepted(self, legitimate_input):
        """Legitimate identifiers must be accepted."""
        result = sql_generate(
            metric=legitimate_input,
            table="test_table",
            dimensions=None,
        )
        assert result.get("sql"), f"Legitimate identifier rejected: {legitimate_input}"
        assert result.get("valid"), f"Legitimate identifier invalid: {legitimate_input}"

    def test_sql_validate_blocks_drop(self):
        """SQL with DROP keyword is blocked."""
        valid, msg = _validate_sql("DROP TABLE users")
        assert not valid
        assert "DROP" in msg.upper()

    def test_sql_validate_blocks_delete(self):
        """SQL with DELETE keyword is blocked."""
        valid, msg = _validate_sql("DELETE FROM users WHERE 1=1")
        assert not valid
        assert "DELETE" in msg.upper()

    def test_sql_validate_blocks_insert(self):
        """SQL with INSERT keyword is blocked."""
        valid, msg = _validate_sql("INSERT INTO users VALUES (1)")
        assert not valid

    def test_sql_validate_blocks_update(self):
        """SQL with UPDATE keyword is blocked."""
        valid, msg = _validate_sql("UPDATE users SET role='admin'")
        assert not valid

    def test_sql_validate_allows_select(self):
        """Valid SELECT queries are allowed."""
        valid, msg = _validate_sql('SELECT "revenue" FROM "sales_table" GROUP BY "region"')
        assert valid

    def test_generated_sql_is_safe(self):
        """Generated SQL uses quoted values, not unescaped interpolation."""
        result = sql_generate(
            metric="revenue",
            table="sales_data",
            dimensions=["region"],
            filters={"region": "North"},
        )
        assert result.get("valid"), f"SQL not valid: {result}"
        sql = result.get("sql", "")
        assert "'North'" in sql  # quoted properly
        assert "DROP" not in sql.upper()

    def test_filter_value_escape(self):
        """A single quote inside a filter value cannot break out of the literal."""
        result = sql_generate(
            metric="revenue",
            table="sales_data",
            filters={"region": "North' OR '1'='1"},
        )
        sql = result.get("sql", "")
        # The quote must be doubled (SQL escaping), never raw
        assert "''" in sql
        # And the semantic meaning must stay a literal comparison
        stripped = re_sub_quotes(sql)
        assert "OR" not in stripped or "1=1" not in stripped

    def test_alias_cannot_break_out(self):
        """Raw metric text must never leak into the alias identifier."""
        result = sql_generate(
            metric='revenue" ; DROP TABLE users; --',
            table="sales_data",
            dimensions=None,
        )
        sql = result.get("sql", "")
        assert '" ;' not in sql
        # DROP may only appear fused inside a sanitized identifier token
        # (e.g. revenueDROPTABLEusers) — never as a standalone keyword
        # outside string literals, which would be executable.
        stripped = re_sub_quotes(sql)
        for kw in ["DROP", "DELETE"]:
            assert not re_search(r"\b" + kw + r"\b", stripped), f"standalone {kw} in: {sql}"


def re_sub_quotes(sql: str) -> str:
    """Strip quoted string literals so keyword checks see only code tokens."""
    import re
    stripped = re.sub(r"'[^']*'", "", sql)
    stripped = re.sub(r'"[^"]*"', "", stripped)
    return stripped


def re_search(pattern: str, text: str):
    import re
    return re.search(pattern, text, re.IGNORECASE)
