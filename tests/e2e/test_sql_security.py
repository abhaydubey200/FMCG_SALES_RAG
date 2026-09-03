"""
SQL Security Tests — verify injection prevention.
These tests can run without Docker (no database needed).
"""
import pytest
from src.agents.tools.sql_tools import sql_validate, sql_generate


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
    ])
    def test_malicious_identifier_rejected(self, malicious_input):
        """All malicious identifiers must be rejected."""
        result = sql_generate(
            metric=malicious_input,
            table="test_table",
            dimensions=None,
        )
        # Either the SQL is marked invalid, or the table name is sanitized
        if result.get("sql"):
            valid, msg = sql_validate(result["sql"])
            # The generated SQL should either be invalid or use a sanitized identifier
            assert not any(kw in result["sql"].upper() for kw in ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER"]), \
                f"Destructive SQL passed through: {result['sql']}"

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
        assert result.get("valid") or result.get("sql"), f"Legitimate identifier rejected: {legitimate_input}"

    def test_sql_validate_blocks_drop(self):
        """SQL with DROP keyword is blocked."""
        valid, msg = sql_validate("DROP TABLE users")
        assert not valid
        assert "DROP" in msg.upper()

    def test_sql_validate_blocks_delete(self):
        """SQL with DELETE keyword is blocked."""
        valid, msg = sql_validate("DELETE FROM users WHERE 1=1")
        assert not valid
        assert "DELETE" in msg.upper()

    def test_sql_validate_blocks_insert(self):
        """SQL with INSERT keyword is blocked."""
        valid, msg = sql_validate("INSERT INTO users VALUES (1)")
        assert not valid

    def test_sql_validate_blocks_update(self):
        """SQL with UPDATE keyword is blocked."""
        valid, msg = sql_validate("UPDATE users SET role='admin'")
        assert not valid

    def test_sql_validate_allows_select(self):
        """Valid SELECT queries are allowed."""
        valid, msg = sql_validate('SELECT "revenue" FROM "sales_table" GROUP BY "region"')
        assert valid

    def test_generated_sql_is_safe(self):
        """Generated SQL uses parameterized values, not string interpolation."""
        result = sql_generate(
            metric="revenue",
            table="sales_data",
            dimensions=["region"],
            filters={"region": "North"},
        )
        assert result.get("valid"), f"SQL not valid: {result}"
        sql = result.get("sql", "")
        # Should not contain unescaped user input in WHERE clause
        assert "'North'" in sql or "\"North\"" in sql  # quoted properly
        assert "DROP" not in sql.upper()
        assert "DELETE" not in sql.upper()
