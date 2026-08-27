"""
Generate test datasets for verifying the dynamic data engine.
Creates three materially different test datasets with different column names
to verify schema-flexible semantic mapping.
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd


def create_dataset_a():
    """Dataset A: Standard sales format with revenue, quantity, discount."""
    data = {
        "sales_date": [
            "2025-01-15", "2025-01-15", "2025-01-20", "2025-02-01", "2025-02-05",
            "2025-02-10", "2025-02-15", "2025-03-01", "2025-03-05", "2025-03-10",
            "2025-03-15", "2025-03-20", "2025-04-01", "2025-04-05", "2025-04-10",
            "2025-04-15", "2025-04-20", "2025-05-01", "2025-05-05", "2025-05-10",
        ],
        "product": [
            "Widget Alpha", "Widget Beta", "Widget Alpha", "Widget Gamma", "Widget Beta",
            "Widget Alpha", "Widget Gamma", "Widget Alpha", "Widget Beta", "Widget Gamma",
            "Widget Alpha", "Widget Beta", "Widget Gamma", "Widget Alpha", "Widget Beta",
            "Widget Gamma", "Widget Alpha", "Widget Beta", "Widget Gamma", "Widget Alpha",
        ],
        "region": [
            "North", "South", "East", "North", "West",
            "South", "East", "North", "South", "West",
            "East", "North", "South", "West", "East",
            "North", "South", "West", "East", "North",
        ],
        "revenue": [
            12500, 8750, 11200, 15600, 9300,
            13400, 14200, 11800, 7600, 16900,
            12100, 8900, 17500, 13000, 9100,
            18200, 12800, 8500, 16300, 13500,
        ],
        "quantity": [
            150, 95, 130, 200, 110,
            160, 185, 140, 88, 220,
            145, 102, 230, 155, 108,
            240, 152, 98, 210, 165,
        ],
        "discount_pct": [
            5.0, 3.2, 7.5, 2.0, 4.0,
            6.1, 3.5, 8.0, 2.5, 1.8,
            5.5, 4.2, 1.5, 6.8, 3.0,
            2.2, 7.0, 3.8, 2.8, 4.5,
        ],
    }
    return pd.DataFrame(data)


def create_dataset_b():
    """Dataset B: Different naming convention — net_sales, units_sold, territory."""
    data = {
        "transaction_date": [
            "2025-01-10", "2025-01-15", "2025-01-20", "2025-02-01", "2025-02-05",
            "2025-02-10", "2025-02-15", "2025-03-01", "2025-03-05", "2025-03-10",
            "2025-03-15", "2025-03-20", "2025-04-01", "2025-04-05", "2025-04-10",
        ],
        "sku": [
            "SKU-001", "SKU-002", "SKU-003", "SKU-001", "SKU-002",
            "SKU-003", "SKU-001", "SKU-002", "SKU-003", "SKU-001",
            "SKU-002", "SKU-003", "SKU-001", "SKU-002", "SKU-003",
        ],
        "territory": [
            "Northeast", "Southeast", "Midwest", "Northeast", "Southeast",
            "West", "South", "Northeast", "Southeast", "West",
            "Midwest", "South", "Northeast", "Southeast", "West",
        ],
        "net_sales": [
            18900, 12300, 15600, 19500, 11800,
            14200, 17600, 13100, 16400, 18200,
            12700, 15900, 20100, 13500, 17100,
        ],
        "units_sold": [
            225, 140, 185, 235, 132,
            170, 210, 150, 198, 220,
            145, 190, 245, 158, 205,
        ],
    }
    return pd.DataFrame(data)


def create_dataset_c():
    """Dataset C: Another variation — order_day, item_name, sales_amount, volume."""
    data = {
        "order_day": [
            "2025-01-05", "2025-01-12", "2025-01-19", "2025-02-02", "2025-02-09",
            "2025-02-16", "2025-03-03", "2025-03-10", "2025-03-17", "2025-03-24",
            "2025-04-07", "2025-04-14", "2025-04-21", "2025-05-05", "2025-05-12",
        ],
        "item_name": [
            "Gadget Pro", "Gadget Lite", "Gadget Pro", "Gadget Ultra", "Gadget Lite",
            "Gadget Pro", "Gadget Ultra", "Gadget Lite", "Gadget Pro", "Gadget Ultra",
            "Gadget Pro", "Gadget Lite", "Gadget Ultra", "Gadget Pro", "Gadget Lite",
        ],
        "market": [
            "EMEA", "APAC", "Americas", "EMEA", "APAC",
            "Americas", "EMEA", "APAC", "Americas", "EMEA",
            "APAC", "Americas", "EMEA", "APAC", "Americas",
        ],
        "sales_amount": [
            22400, 9800, 16500, 28900, 10200,
            18300, 31200, 11500, 19800, 27600,
            24100, 12800, 29400, 21700, 13500,
        ],
        "volume": [
            280, 120, 200, 350, 125,
            225, 380, 140, 240, 330,
            295, 155, 355, 265, 165,
        ],
    }
    return pd.DataFrame(data)


def save_test_datasets(output_dir: str = "tests/test_datasets"):
    """Save all test datasets."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    datasets = {
        "sales_dataset_a.csv": create_dataset_a(),
        "sales_dataset_b.csv": create_dataset_b(),
        "sales_dataset_c.csv": create_dataset_c(),
    }

    for filename, df in datasets.items():
        filepath = output_path / filename
        df.to_csv(filepath, index=False)
        print(f"Created {filename}: {len(df)} rows, {len(df.columns)} columns")
        print(f"  Columns: {list(df.columns)}")
        print(f"  Domain hint: {'sales' if 'revenue' in df.columns or 'net_sales' in df.columns else 'mixed'}")
        print()

    print(f"All test datasets saved to {output_path}")
    return datasets


if __name__ == "__main__":
    save_test_datasets()
