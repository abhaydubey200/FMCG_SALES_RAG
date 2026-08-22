"""
Synthetic Amazon-style Sales & Marketing dataset generator.

Design notes (documented per README Section 4 "Dataset design"):
- Volumes exceed the assignment minimums (120 products, 6000 sales,
  24 campaigns, 1200 reviews, 600 customers).
- One product ("Aurora Pro Wireless Earbuds") is deliberately engineered
  with a Q2 sales decline driven by a *combination* of a discount cut and
  a marketing spend cut, with a matching dip in review sentiment — this
  gives the diagnostic-question test cases (Section 9D) real, non-fabricated
  evidence to retrieve instead of relying on the LLM to invent a story.
- Dates span 18 months (2024-08 through 2026-01) so growth %, seasonality
  and "Q2 decline" style questions are answerable from real data.
"""
import random
import sqlite3
import string
from datetime import date, timedelta

import numpy as np

from src import config

random.seed(config.RANDOM_SEED)
np.random.seed(config.RANDOM_SEED)

CATEGORIES = {
    "Electronics": ["Headphones", "Smart Home", "Wearables", "Laptops", "Cameras", "Accessories"],
    "Home & Kitchen": ["Cookware", "Small Appliances", "Storage", "Furniture", "Decor"],
    "Fashion": ["Men's Apparel", "Women's Apparel", "Footwear", "Bags", "Jewelry"],
    "Beauty": ["Skincare", "Haircare", "Makeup", "Fragrance"],
    "Sports & Outdoors": ["Fitness Equipment", "Camping", "Cycling", "Team Sports"],
    "Toys & Games": ["Board Games", "Action Figures", "Educational", "Outdoor Play"],
    "Books": ["Fiction", "Non-Fiction", "Children's", "Self-Help"],
    "Grocery": ["Snacks", "Beverages", "Pantry", "Organic"],
}

CHANNELS = ["Search Ads", "Social Media", "Display", "Email", "Influencer", "Affiliate"]
REGIONS = ["North America", "Europe", "APAC", "Latin America", "Middle East"]
SEGMENTS = ["Premium", "Regular", "Budget", "New Customer"]
ACQUISITION_CHANNELS = ["Organic Search", "Paid Search", "Social Media", "Referral", "Email", "Direct"]

ADJ = ["Aurora", "Nimbus", "Vertex", "Solace", "Crest", "Halo", "Ember", "Quartz", "Zenith", "Marlow",
       "Lumen", "Cobalt", "Terra", "Onyx", "Pulse", "Meridian", "Sable", "Drift", "Fable", "Grove"]
NOUN = {
    "Headphones": ["Wireless Earbuds", "Over-Ear Headphones", "Sport Earphones"],
    "Smart Home": ["Smart Plug", "Video Doorbell", "Smart Bulb Kit"],
    "Wearables": ["Fitness Tracker", "Smartwatch", "Sleep Ring"],
    "Laptops": ["Ultrabook 14", "Convertible Laptop", "Gaming Laptop"],
    "Cameras": ["Action Camera", "Mirrorless Camera", "Webcam Pro"],
    "Accessories": ["USB-C Hub", "Wireless Charger", "Laptop Stand"],
    "Cookware": ["Non-Stick Pan Set", "Cast Iron Skillet", "Cookware Set"],
    "Small Appliances": ["Air Fryer", "Espresso Machine", "Blender Pro"],
    "Storage": ["Storage Bin Set", "Closet Organizer", "Pantry Rack"],
    "Furniture": ["Accent Chair", "Coffee Table", "Bookshelf"],
    "Decor": ["Wall Art Set", "Table Lamp", "Area Rug"],
    "Men's Apparel": ["Slim Fit Shirt", "Chino Pants", "Bomber Jacket"],
    "Women's Apparel": ["Wrap Dress", "High-Rise Jeans", "Knit Cardigan"],
    "Footwear": ["Running Shoes", "Canvas Sneakers", "Leather Boots"],
    "Bags": ["Tote Bag", "Backpack", "Crossbody Bag"],
    "Jewelry": ["Pendant Necklace", "Stud Earrings", "Charm Bracelet"],
    "Skincare": ["Vitamin C Serum", "Hydrating Moisturizer", "Clay Mask"],
    "Haircare": ["Repair Shampoo", "Argan Hair Oil", "Curl Cream"],
    "Makeup": ["Matte Lipstick", "Foundation", "Eyeshadow Palette"],
    "Fragrance": ["Eau de Parfum", "Body Mist", "Scented Candle"],
    "Fitness Equipment": ["Adjustable Dumbbells", "Yoga Mat", "Resistance Bands"],
    "Camping": ["2-Person Tent", "Sleeping Bag", "Camp Stove"],
    "Cycling": ["Road Bike Helmet", "Bike Lock", "Cycling Gloves"],
    "Team Sports": ["Soccer Ball", "Basketball", "Badminton Set"],
    "Board Games": ["Strategy Board Game", "Family Card Game", "Puzzle 1000pc"],
    "Action Figures": ["Collectible Figure Set", "Poseable Action Figure"],
    "Educational": ["STEM Building Kit", "Coding Robot Kit"],
    "Outdoor Play": ["Trampoline", "Kids Scooter", "Water Blaster"],
    "Fiction": ["Mystery Novel", "Fantasy Epic", "Literary Fiction"],
    "Non-Fiction": ["Popular Science Book", "Memoir", "History Book"],
    "Children's": ["Picture Book", "Early Reader Set"],
    "Self-Help": ["Productivity Guide", "Mindfulness Journal"],
    "Snacks": ["Trail Mix Pack", "Protein Bar Box", "Popcorn Variety Pack"],
    "Beverages": ["Cold Brew Coffee Pack", "Sparkling Water Case", "Herbal Tea Set"],
    "Pantry": ["Organic Pasta Pack", "Olive Oil Bottle", "Spice Set"],
    "Organic": ["Organic Granola", "Organic Honey Jar", "Organic Quinoa Pack"],
}

FLAGSHIP_PRODUCT_NAME = "Aurora Pro Wireless Earbuds"
FLAGSHIP_PRODUCT_ID = "P0001"


def _rand_id(prefix, n, width=6):
    return f"{prefix}{str(n).zfill(width)}"


def gen_products():
    rows = []
    pid_counter = 1
    # Force flagship product first
    rows.append({
        "product_id": FLAGSHIP_PRODUCT_ID,
        "product_name": FLAGSHIP_PRODUCT_NAME,
        "category": "Electronics",
        "subcategory": "Headphones",
        "price": 89.99,
        "cost": 34.00,
        "rating": 4.1,
        "review_count": 0,  # filled after reviews generated
    })
    pid_counter += 1
    while len(rows) < config.N_PRODUCTS:
        category = random.choice(list(CATEGORIES.keys()))
        subcategory = random.choice(CATEGORIES[category])
        base_noun = random.choice(NOUN[subcategory])
        name = f"{random.choice(ADJ)} {base_noun}"
        price = round(random.uniform(8, 450), 2)
        cost = round(price * random.uniform(0.35, 0.65), 2)
        rows.append({
            "product_id": _rand_id("P", pid_counter, 4),
            "product_name": name,
            "category": category,
            "subcategory": subcategory,
            "price": price,
            "cost": cost,
            "rating": round(random.uniform(3.0, 5.0), 1),
            "review_count": 0,
        })
        pid_counter += 1
    return rows


def _daterange(start, end):
    days = (end - start).days
    return [start + timedelta(days=i) for i in range(days + 1)]


def gen_customers():
    rows = []
    start = date(2023, 1, 1)
    end = date(2026, 1, 1)
    for i in range(1, config.N_CUSTOMERS + 1):
        first_purchase = start + timedelta(days=random.randint(0, (end - start).days))
        segment = random.choices(SEGMENTS, weights=[0.15, 0.45, 0.25, 0.15])[0]
        ltv_base = {"Premium": (1500, 6000), "Regular": (400, 1500), "Budget": (100, 500), "New Customer": (20, 200)}[segment]
        rows.append({
            "customer_id": _rand_id("C", i, 5),
            "segment": segment,
            "region": random.choice(REGIONS),
            "acquisition_channel": random.choice(ACQUISITION_CHANNELS),
            "first_purchase_date": first_purchase.isoformat(),
            "lifetime_value": round(random.uniform(*ltv_base), 2),
        })
    return rows


def gen_sales(products, customers):
    rows = []
    order_start = date(2024, 8, 1)
    order_end = date(2026, 1, 31)
    product_ids = [p["product_id"] for p in products]
    customer_ids = [c["customer_id"] for c in customers]
    products_by_id = {p["product_id"]: p for p in products}

    # weight products so a handful are "bestsellers" (fatter tail realism)
    weights = np.random.pareto(2.2, size=len(product_ids)) + 0.1

    n = 1
    while len(rows) < config.N_SALES:
        pid = random.choices(product_ids, weights=weights, k=1)[0]
        product = products_by_id[pid]
        order_date = order_start + timedelta(days=random.randint(0, (order_end - order_start).days))

        discount = round(random.choice([0, 0, 0, 5, 10, 10, 15, 20, 25]), 2)

        # Flagship product: engineered Q2 2025 decline story.
        # Apr-Jun 2025: discount cut from typical ~15% to ~5%, and volume drops.
        if pid == FLAGSHIP_PRODUCT_ID:
            if date(2025, 4, 1) <= order_date <= date(2025, 6, 30):
                discount = round(random.choice([0, 0, 5, 5, 5, 10]), 2)
                qty_weight = 0.35  # demand suppressed in this window
            elif order_date > date(2025, 6, 30):
                discount = round(random.choice([0, 5, 10, 10, 15]), 2)
                qty_weight = 0.7  # partial recovery post-Q2
            else:
                discount = round(random.choice([10, 15, 15, 20]), 2)
                qty_weight = 1.0
        else:
            qty_weight = 1.0

        quantity = max(1, int(np.random.poisson(2.2 * qty_weight)) or 1)
        selling_price = round(product["price"] * (1 - discount / 100), 2)
        revenue = round(selling_price * quantity, 2)
        cost = round(product["cost"] * quantity, 2)

        rows.append({
            "order_id": _rand_id("O", n, 7),
            "order_date": order_date.isoformat(),
            "product_id": pid,
            "customer_id": random.choice(customer_ids),
            "quantity": quantity,
            "selling_price": selling_price,
            "discount": discount,
            "revenue": revenue,
            "cost": cost,
        })
        n += 1
    return rows


def gen_campaigns(products):
    rows = []
    product_ids = [p["product_id"] for p in products]
    start_window = date(2024, 8, 1)
    end_window = date(2026, 1, 31)
    names = ["Summer", "Spring Refresh", "Back to School", "Holiday", "New Year", "Flash Sale",
             "Prime-Style Days", "Category Spotlight", "Loyalty Push", "Clearance", "Launch Week", "Winter"]
    for i in range(1, config.N_CAMPAIGNS + 1):
        pid = random.choice(product_ids)
        cat = None
        channel = random.choice(CHANNELS)
        cstart = start_window + timedelta(days=random.randint(0, (end_window - start_window).days - 30))
        cend = cstart + timedelta(days=random.randint(7, 30))
        impressions = random.randint(20000, 900000)
        ctr = random.uniform(0.006, 0.045)
        clicks = int(impressions * ctr)
        conv_rate = random.uniform(0.01, 0.09)
        conversions = max(1, int(clicks * conv_rate))
        spend = round(clicks * random.uniform(0.25, 2.2), 2)

        # Flagship product's Q2 2025 campaign spend cut (part of the decline story)
        if pid == FLAGSHIP_PRODUCT_ID and date(2025, 4, 1) <= cstart <= date(2025, 6, 30):
            spend = round(spend * 0.4, 2)
            conversions = max(1, int(conversions * 0.5))

        avg_order_value = random.uniform(25, 220)
        attributed_revenue = round(conversions * avg_order_value, 2)
        rows.append({
            "campaign_id": _rand_id("CMP", i, 4),
            "campaign_name": f"{random.choice(names)} {random.choice(list(CATEGORIES.keys()))} Campaign",
            "product_id": pid,
            "channel": channel,
            "start_date": cstart.isoformat(),
            "end_date": cend.isoformat(),
            "impressions": impressions,
            "clicks": clicks,
            "spend": spend,
            "conversions": conversions,
            "attributed_revenue": attributed_revenue,
        })
    return rows


POSITIVE_SNIPPETS = [
    "Works great and arrived on time.", "Exceeded my expectations for the price.",
    "Battery life is excellent and setup was easy.", "Would definitely buy again.",
    "Quality feels premium, very happy with this purchase.", "Exactly as described, no complaints.",
]
NEUTRAL_SNIPPETS = [
    "It's okay, does the job but nothing special.", "Decent for the price, a few minor issues.",
    "Average product, packaging could be better.",
]
NEGATIVE_SNIPPETS = [
    "Stopped working after two weeks.", "Not worth the price, disappointed.",
    "Connectivity kept dropping, had to return it.", "Fit/quality was worse than expected.",
    "Customer support was unhelpful when I had an issue.",
]
FLAGSHIP_NEGATIVE = [
    "Battery life got noticeably worse after a firmware update.",
    "Right earbud disconnects randomly during calls.",
    "Feels like build quality dropped compared to when I first bought it.",
    "Started having Bluetooth pairing issues in Q2.",
]


def gen_reviews(products):
    rows = []
    product_ids = [p["product_id"] for p in products]
    weights = np.random.pareto(1.8, size=len(product_ids)) + 0.1
    # Guarantee the flagship product gets meaningful review volume so the
    # diagnostic-question evidence (Q2 2025 sentiment dip) is retrievable.
    flagship_idx = product_ids.index(FLAGSHIP_PRODUCT_ID)
    weights[flagship_idx] = max(weights) * 1.5
    start = date(2024, 8, 1)
    end = date(2026, 1, 31)
    for i in range(1, config.N_REVIEWS + 1):
        pid = random.choices(product_ids, weights=weights, k=1)[0]
        review_date = start + timedelta(days=random.randint(0, (end - start).days))

        if pid == FLAGSHIP_PRODUCT_ID and date(2025, 4, 1) <= review_date <= date(2025, 7, 31):
            rating = random.choices([1, 2, 3, 4, 5], weights=[0.25, 0.30, 0.25, 0.15, 0.05])[0]
            text = random.choice(FLAGSHIP_NEGATIVE) if rating <= 3 else random.choice(POSITIVE_SNIPPETS)
        else:
            rating = random.choices([1, 2, 3, 4, 5], weights=[0.05, 0.08, 0.15, 0.35, 0.37])[0]
            if rating >= 4:
                text = random.choice(POSITIVE_SNIPPETS)
            elif rating == 3:
                text = random.choice(NEUTRAL_SNIPPETS)
            else:
                text = random.choice(NEGATIVE_SNIPPETS)

        rows.append({
            "review_id": _rand_id("R", i, 6),
            "product_id": pid,
            "rating": rating,
            "review_text": text,
            "review_date": review_date.isoformat(),
        })
    return rows


def build_database():
    conn = sqlite3.connect(config.DB_PATH)
    cur = conn.cursor()
    cur.executescript("""
    DROP TABLE IF EXISTS products;
    DROP TABLE IF EXISTS sales;
    DROP TABLE IF EXISTS campaigns;
    DROP TABLE IF EXISTS customers;
    DROP TABLE IF EXISTS reviews;

    CREATE TABLE products (
        product_id TEXT PRIMARY KEY,
        product_name TEXT,
        category TEXT,
        subcategory TEXT,
        price REAL,
        cost REAL,
        rating REAL,
        review_count INTEGER
    );
    CREATE TABLE sales (
        order_id TEXT PRIMARY KEY,
        order_date TEXT,
        product_id TEXT,
        customer_id TEXT,
        quantity INTEGER,
        selling_price REAL,
        discount REAL,
        revenue REAL,
        cost REAL
    );
    CREATE TABLE campaigns (
        campaign_id TEXT PRIMARY KEY,
        campaign_name TEXT,
        product_id TEXT,
        channel TEXT,
        start_date TEXT,
        end_date TEXT,
        impressions INTEGER,
        clicks INTEGER,
        spend REAL,
        conversions INTEGER,
        attributed_revenue REAL
    );
    CREATE TABLE customers (
        customer_id TEXT PRIMARY KEY,
        segment TEXT,
        region TEXT,
        acquisition_channel TEXT,
        first_purchase_date TEXT,
        lifetime_value REAL
    );
    CREATE TABLE reviews (
        review_id TEXT PRIMARY KEY,
        product_id TEXT,
        rating INTEGER,
        review_text TEXT,
        review_date TEXT
    );
    CREATE INDEX idx_sales_product ON sales(product_id);
    CREATE INDEX idx_sales_date ON sales(order_date);
    CREATE INDEX idx_campaigns_product ON campaigns(product_id);
    CREATE INDEX idx_reviews_product ON reviews(product_id);
    CREATE INDEX idx_products_category ON products(category);
    """)

    products = gen_products()
    customers = gen_customers()
    sales = gen_sales(products, customers)
    campaigns = gen_campaigns(products)
    reviews = gen_reviews(products)

    # backfill review_count / rating from actual reviews for consistency
    from collections import defaultdict
    counts = defaultdict(list)
    for r in reviews:
        counts[r["product_id"]].append(r["rating"])
    for p in products:
        ratings = counts.get(p["product_id"], [])
        if ratings:
            p["review_count"] = len(ratings)
            p["rating"] = round(sum(ratings) / len(ratings), 1)

    cur.executemany(
        "INSERT INTO products VALUES (:product_id,:product_name,:category,:subcategory,:price,:cost,:rating,:review_count)",
        products)
    cur.executemany(
        "INSERT INTO sales VALUES (:order_id,:order_date,:product_id,:customer_id,:quantity,:selling_price,:discount,:revenue,:cost)",
        sales)
    cur.executemany(
        "INSERT INTO campaigns VALUES (:campaign_id,:campaign_name,:product_id,:channel,:start_date,:end_date,:impressions,:clicks,:spend,:conversions,:attributed_revenue)",
        campaigns)
    cur.executemany(
        "INSERT INTO customers VALUES (:customer_id,:segment,:region,:acquisition_channel,:first_purchase_date,:lifetime_value)",
        customers)
    cur.executemany(
        "INSERT INTO reviews VALUES (:review_id,:product_id,:rating,:review_text,:review_date)",
        reviews)

    conn.commit()
    conn.close()
    print(f"Generated: {len(products)} products, {len(sales)} sales, {len(campaigns)} campaigns, "
          f"{len(customers)} customers, {len(reviews)} reviews -> {config.DB_PATH}")


if __name__ == "__main__":
    build_database()
