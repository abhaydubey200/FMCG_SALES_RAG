"""
Tests for dynamic analytics engine functions.

These tests verify the workspace-aware functions that replaced the
legacy hardcoded query functions.
"""
import pytest

from src.analytics.dynamic_engine import (
    has_workspace_data,
    get_workspace_tables,
    workspace_total_revenue,
    workspace_total_quantity,
    workspace_total_spend,
    workspace_revenue_by_dimension,
    workspace_revenue_trend,
    workspace_top_entities,
    workspace_row_count,
    discover_available_data,
    get_available_kpis,
)


def test_has_workspace_data_returns_bool():
    result = has_workspace_data()
    assert isinstance(result, bool)


def test_get_workspace_tables_returns_list():
    result = get_workspace_tables()
    assert isinstance(result, list)


def test_workspace_total_revenue_returns_float_or_none():
    result = workspace_total_revenue()
    assert result is None or isinstance(result, float)


def test_workspace_total_quantity_returns_float_or_none():
    result = workspace_total_quantity()
    assert result is None or isinstance(result, float)


def test_workspace_total_spend_returns_float_or_none():
    result = workspace_total_spend()
    assert result is None or isinstance(result, float)


def test_workspace_revenue_by_dimension_returns_list():
    for dim in ["region", "product", "category", "territory", "market"]:
        result = workspace_revenue_by_dimension(dim)
        assert isinstance(result, list)


def test_workspace_revenue_trend_returns_list():
    result = workspace_revenue_trend()
    assert isinstance(result, list)


def test_workspace_top_entities_returns_list():
    result = workspace_top_entities(limit=5)
    assert isinstance(result, list)
    assert len(result) <= 5


def test_workspace_row_count_returns_int():
    result = workspace_row_count()
    assert isinstance(result, int)
    assert result >= 0


def test_discover_available_data_returns_dict():
    result = discover_available_data()
    assert isinstance(result, dict)
    assert "assets" in result
    assert "available_measures" in result
    assert "available_dimensions" in result


def test_get_available_kpis_returns_list():
    result = get_available_kpis()
    assert isinstance(result, list)
