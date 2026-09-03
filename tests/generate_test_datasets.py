#!/usr/bin/env python3
"""Generate test datasets with exact ground-truth revenue totals."""
import csv, os
from decimal import Decimal, ROUND_HALF_UP

def d(val):
    return float(Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_datasets")
os.makedirs(OUT, exist_ok=True)

# Raw revenue values (will be scaled to hit exact targets)
v_a_raw = [14520,12835,11495,8400,22650,9438,6720,16610,16335,7560,13892,16940,9240,10268,12705,7980,18875,10648,7350,21895,13310,8820,14798,15730,6510,18120,11495,9660,11325,13915,7770,21140,19360,8400,16308]
v_b_raw = [11858,18120,7350,17545,13288,8820,13310,23405,8190,9922,19630,9450,15488,14345,6930,16698,16912,7980,12342,22348,7560,10890,24160,8400,14278,15855,10080,15972,21442,6510]
v_c_raw = [10648,17365,7980,15730,11325,8610,12342,20838,7140,14278,14345,9030,17182,16308,7770,11495,23858,8400,15125,12382]

targets = {"A": 366979.88, "B": 328460.90, "C": 255697.35}

def scale_and_adjust(raw_vals, target):
    scale = target / sum(raw_vals)
    vals = [d(x * scale) for x in raw_vals]
    vals[-1] = d(vals[-1] + d(target - d(sum(vals))))
    return vals

v_a = scale_and_adjust(v_a_raw, targets["A"])
v_b = scale_and_adjust(v_b_raw, targets["B"])
v_c = scale_and_adjust(v_c_raw, targets["C"])

# Dataset A: sales_region_north.csv
dates_a = ["2025-01-15","2025-01-22","2025-02-03","2025-02-14","2025-02-28","2025-03-05","2025-03-12","2025-03-20","2025-04-01","2025-04-10","2025-04-18","2025-05-02","2025-05-15","2025-05-28","2025-06-03","2025-06-12","2025-06-25","2025-07-01","2025-07-10","2025-07-22","2025-08-05","2025-08-15","2025-08-28","2025-09-02","2025-09-14","2025-09-25","2025-10-01","2025-10-10","2025-10-22","2025-11-05","2025-11-15","2025-11-28","2025-12-03","2025-12-12","2025-12-20"]
prods = ["Widget Alpha","Gadget Beta"]
cats = {"Widget Alpha": "Electronics", "Gadget Beta": "Electronics", "Tool Gamma": "Home & Garden"}
prod_cycle_a = ["Widget Alpha","Gadget Beta","Widget Alpha","Tool Gamma","Gadget Beta","Widget Alpha","Tool Gamma","Gadget Beta","Widget Alpha","Tool Gamma","Gadget Beta","Widget Alpha","Tool Gamma","Gadget Beta","Widget Alpha","Tool Gamma","Gadget Beta","Widget Alpha","Tool Gamma","Gadget Beta","Widget Alpha","Tool Gamma","Gadget Beta","Widget Alpha","Tool Gamma","Gadget Beta","Widget Alpha","Tool Gamma","Gadget Beta","Widget Alpha","Tool Gamma","Gadget Beta","Widget Alpha","Tool Gamma","Gadget Beta"]
qty_a = [120,85,95,200,150,78,160,110,135,180,92,140,220,68,105,190,125,88,175,145,110,210,98,130,155,120,95,230,75,115,185,140,160,200,108]
camps_a = ["Promo-Spring","Promo-Spring","Promo-Spring","Channel-Direct","Promo-Spring","Channel-Retail","Channel-Direct","Promo-Summer","Promo-Summer","Channel-Direct","Promo-Summer","Channel-Retail","Channel-Direct","Promo-Summer","Channel-Retail","Channel-Direct","Promo-Summer","Promo-Fall","Channel-Direct","Promo-Fall","Channel-Retail","Channel-Direct","Promo-Fall","Promo-Fall","Channel-Direct","Channel-Retail","Promo-Holiday","Channel-Direct","Promo-Holiday","Channel-Retail","Channel-Direct","Promo-Holiday","Promo-Holiday","Channel-Direct","Promo-Holiday"]
disc_a = [5.0,3.5,4.0,0.0,6.0,2.5,0.0,5.5,4.5,1.0,3.0,5.0,0.5,4.0,2.0,0.0,6.5,3.5,1.5,5.0,4.0,0.0,3.0,5.5,2.0,4.5,6.0,0.5,3.5,2.5,1.0,5.0,7.0,0.0,4.5]

with open(os.path.join(OUT, "sales_region_north.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["order_id","date","product","category","region","quantity","revenue","customer","campaign","discount_pct"])
    for i in range(35):
        p = prod_cycle_a[i]
        w.writerow([f"ORD-{1001+i}", dates_a[i], p, cats[p], "North", qty_a[i], v_a[i], f"CUST-{i+1:03d}", camps_a[i], disc_a[i]])

# Dataset B: sales_region_south.csv
dates_b = ["2025-01-10","2025-01-20","2025-02-05","2025-02-18","2025-03-01","2025-03-15","2025-04-02","2025-04-12","2025-04-25","2025-05-08","2025-05-18","2025-06-01","2025-06-14","2025-06-28","2025-07-05","2025-07-18","2025-08-01","2025-08-15","2025-08-28","2025-09-10","2025-09-22","2025-10-05","2025-10-18","2025-11-01","2025-11-12","2025-11-25","2025-12-08","2025-12-15","2025-12-22","2025-12-30"]
prod_cycle_b = ["Widget Alpha","Gadget Beta","Tool Gamma","Widget Alpha","Gadget Beta","Tool Gamma","Widget Alpha","Gadget Beta","Tool Gamma","Widget Alpha","Gadget Beta","Tool Gamma","Widget Alpha","Gadget Beta","Tool Gamma","Widget Alpha","Gadget Beta","Tool Gamma","Widget Alpha","Gadget Beta","Tool Gamma","Widget Alpha","Gadget Beta","Tool Gamma","Widget Alpha","Gadget Beta","Tool Gamma","Widget Alpha","Gadget Beta","Tool Gamma"]
qty_b = [98,120,175,145,88,210,110,155,195,82,130,225,128,95,165,138,112,190,102,148,180,90,160,200,118,105,240,132,142,155]
camps_b = ["Deal-Winter","Deal-Winter","Channel-Online","Deal-Winter","Channel-Online","Channel-Online","Deal-Spring","Deal-Spring","Channel-Online","Channel-Retail","Deal-Spring","Channel-Online","Channel-Retail","Deal-Summer","Channel-Online","Deal-Summer","Deal-Summer","Channel-Online","Channel-Retail","Deal-Fall","Channel-Online","Deal-Fall","Deal-Fall","Channel-Online","Channel-Retail","Deal-Holiday","Channel-Online","Deal-Holiday","Deal-Holiday","Channel-Online"]
disc_b = [4.5,3.0,1.0,5.5,2.0,0.5,4.0,6.0,1.5,3.5,5.0,0.0,2.5,4.5,1.0,3.0,5.5,0.5,4.0,6.5,0.0,3.5,5.0,1.5,2.0,4.0,0.0,5.5,7.0,1.0]

with open(os.path.join(OUT, "sales_region_south.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["transaction_id","order_date","item_name","item_category","territory","units_sold","sales_amount","buyer_name","promo_name","promo_pct"])
    for i in range(30):
        p = prod_cycle_b[i]
        w.writerow([f"TXN-{2001+i}", dates_b[i], p, cats[p], "South", qty_b[i], v_b[i], f"BUYER-{i+1:03d}", camps_b[i], disc_b[i]])

# Dataset C: sales_export_erp.csv
dates_c = ["2025-01-08","2025-01-25","2025-02-10","2025-02-22","2025-03-08","2025-03-20","2025-04-05","2025-04-18","2025-05-02","2025-05-15","2025-05-28","2025-06-10","2025-06-22","2025-07-05","2025-07-18","2025-08-01","2025-08-15","2025-08-28","2025-09-10","2025-09-25"]
prod_cycle_c = ["Widget Alpha","Gadget Beta","Tool Gamma","Widget Alpha","Gadget Beta","Tool Gamma","Widget Alpha","Gadget Beta","Tool Gamma","Widget Alpha","Gadget Beta","Tool Gamma","Widget Alpha","Gadget Beta","Tool Gamma","Widget Alpha","Gadget Beta","Tool Gamma","Widget Alpha","Gadget Beta"]
qty_c = [88,115,190,130,75,205,102,138,170,118,95,215,142,108,185,95,158,200,125,82]
camps_c = ["Export-Q1"]*5 + ["Export-Q2"]*5 + ["Export-Q3"]*5 + ["Export-Q4"]*5
disc_c = [3.0,4.5,1.0,5.0,2.5,0.5,3.5,6.0,1.5,4.0,3.0,0.0,5.5,4.0,1.0,2.5,5.0,0.5,3.5,4.5]

with open(os.path.join(OUT, "sales_export_erp.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["invoice_id","invoice_date","product_name","product_category","market","qty","net_sales","client_id","export_program","markdown_pct"])
    for i in range(20):
        p = prod_cycle_c[i]
        w.writerow([f"EXP-{3001+i}", dates_c[i], p, cats[p], "West", qty_c[i], v_c[i], f"CLIENT-{i+1:03d}", camps_c[i], disc_c[i]])

# Verify
total_a = d(sum(v_a))
total_b = d(sum(v_b))
total_c = d(sum(v_c))
combined = d(total_a + total_b + total_c)
after_del = d(total_b + total_c)

print(f"Dataset A: {total_a} (target {targets['A']}) {'OK' if abs(total_a-targets['A'])<0.01 else 'FAIL'}")
print(f"Dataset B: {total_b} (target {targets['B']}) {'OK' if abs(total_b-targets['B'])<0.01 else 'FAIL'}")
print(f"Dataset C: {total_c} (target {targets['C']}) {'OK' if abs(total_c-targets['C'])<0.01 else 'FAIL'}")
print(f"Combined:  {combined} (target 951138.13) {'OK' if abs(combined-951138.13)<0.01 else 'FAIL'}")
print(f"After del: {after_del} (target 584158.25) {'OK' if abs(after_del-584158.25)<0.01 else 'FAIL'}")

assert abs(total_a - targets["A"]) < 0.01
assert abs(total_b - targets["B"]) < 0.01
assert abs(total_c - targets["C"]) < 0.01
assert abs(combined - 951138.13) < 0.01
assert abs(after_del - 584158.25) < 0.01
print("\nAll assertions passed.")
print(f"Files written to {OUT}")
for fn in sorted(os.listdir(OUT)):
    fpath = os.path.join(OUT, fn)
    with open(fpath) as f:
        lines = f.readlines()
    print(f"  {fn}: {len(lines)-1} data rows")
