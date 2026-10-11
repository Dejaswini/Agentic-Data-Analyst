"""Seed the demo sales database with realistic invented Indian-market data.

Usage:
    python db/seed.py            # uses DATABASE_URL from .env / environment
    python db/seed.py --rows 2000

The data is invented but plausible: Indian regions/cities, FMCG-style
products, seasonal sales across 2024-01-01 .. 2026-09-27.
"""
from __future__ import annotations

import argparse
import os
import random
from datetime import date, timedelta
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

REGIONS = [
    ("Chennai Metro", "Tamil Nadu"),
    ("Coimbatore", "Tamil Nadu"),
    ("Madurai", "Tamil Nadu"),
    ("Kochi", "Kerala"),
    ("Thiruvananthapuram", "Kerala"),
    ("Bengaluru Urban", "Karnataka"),
    ("Mysuru", "Karnataka"),
    ("Hyderabad", "Telangana"),
    ("Vijayawada", "Andhra Pradesh"),
    ("Mumbai West", "Maharashtra"),
    ("Pune", "Maharashtra"),
    ("Kolkata", "West Bengal"),
]

CUSTOMERS = [
    ("Anand Stores", "Chennai", "Retail", 1),
    ("Bharath Traders", "Chennai", "Wholesale", 1),
    ("Chitra Supermarket", "Coimbatore", "Retail", 2),
    ("Dhanush Agencies", "Madurai", "Wholesale", 3),
    ("Eswari Mart", "Chennai", "Retail", 1),
    ("Farhan Enterprises", "Kochi", "Corporate", 4),
    ("Giri Distributors", "Thiruvananthapuram", "Wholesale", 5),
    ("Harini Retail", "Kochi", "Retail", 4),
    ("Ilango & Sons", "Coimbatore", "Wholesale", 2),
    ("Janani Super Bazaar", "Bengaluru", "Retail", 6),
    ("Karthik Wholesale", "Bengaluru", "Wholesale", 6),
    ("Lakshmi Stores", "Mysuru", "Retail", 7),
    ("Meenakshi Traders", "Madurai", "Retail", 3),
    ("Naveen Mart", "Hyderabad", "Retail", 8),
    ("Omkar Agencies", "Hyderabad", "Corporate", 8),
    ("Padma Distributors", "Vijayawada", "Wholesale", 9),
    ("Rajesh Retail House", "Mumbai", "Retail", 10),
    ("Shalini Superstore", "Pune", "Retail", 11),
    ("Thirumalai Traders", "Chennai", "Wholesale", 1),
    ("Uma Corporate Buyers", "Mumbai", "Corporate", 10),
    ("Venkatesh Stores", "Vijayawada", "Retail", 9),
    ("Yamuna Mart", "Kolkata", "Retail", 12),
]

PRODUCTS = [
    ("Arisi Ponni Rice 5kg", "Grocery", 420.00),
    ("Aashirvaad Atta 10kg", "Grocery", 455.00),
    ("Sunflower Oil 1L", "Grocery", 165.00),
    ("Filter Coffee Powder 500g", "Beverages", 340.00),
    ("Green Tea 100 bags", "Beverages", 260.00),
    ("Turmeric Powder 200g", "Grocery", 68.00),
    ("LED Bulb 9W (pack of 4)", "Electronics", 399.00),
    ("Ceiling Fan 1200mm", "Electronics", 2450.00),
    ("Mixer Grinder 750W", "Electronics", 3200.00),
    ("Cotton Bedsheet Double", "Home", 799.00),
    ("Steel Water Bottle 1L", "Home", 349.00),
    ("Non-stick Cookware Set", "Home", 1899.00),
    ("Herbal Shampoo 340ml", "Personal Care", 210.00),
    ("Sandal Soap (pack of 6)", "Personal Care", 180.00),
]

REPS = [
    ("Kavin Raj", 1), ("Divya Sri", 2), ("Manoj Kumar", 3),
    ("Anjali Nair", 4), ("Vishnu Prasad", 5), ("Sneha Rao", 6),
    ("Aravind Samy", 7), ("Fathima Beevi", 8), ("Rohit Shetty", 10),
    ("Priyanka Das", 12),
]

FIRST_DAY = date(2024, 1, 1)
LAST_DAY = date(2026, 9, 27)


def seasonal_multiplier(month: int) -> float:
    # Festival bumps: Apr (New Year/Vishu), Oct-Nov (Diwali), Dec-Jan (Pongal/season)
    return {1: 1.25, 4: 1.2, 10: 1.45, 11: 1.35, 12: 1.15}.get(month, 1.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1600, help="number of sales rows")
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL", "postgresql://ada:ada@localhost:5432/sales_db")
    schema = (Path(__file__).parent / "schema.sql").read_text()
    rng = random.Random(42)

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(schema)
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO regions (region_name, state) VALUES (%s, %s)", REGIONS
            )
            cur.executemany(
                "INSERT INTO customers (customer_name, city, segment, region_id) VALUES (%s, %s, %s, %s)",
                CUSTOMERS,
            )
            cur.executemany(
                "INSERT INTO products (product_name, category, unit_price) VALUES (%s, %s, %s)",
                PRODUCTS,
            )
            cur.executemany(
                "INSERT INTO sales_representatives (rep_name, region_id) VALUES (%s, %s)", REPS
            )

            days = (LAST_DAY - FIRST_DAY).days
            rows = []
            for _ in range(args.rows):
                sale_date = FIRST_DAY + timedelta(days=rng.randint(0, days))
                if rng.random() > seasonal_multiplier(sale_date.month) / 1.5:
                    continue  # thin out off-season months
                product_id = rng.randint(1, len(PRODUCTS))
                base_price = float(PRODUCTS[product_id - 1][2])
                # yearly price drift ~4%
                price = round(base_price * (1 + 0.04 * (sale_date.year - 2024)), 2)
                quantity = rng.choices([1, 2, 3, 5, 8, 12, 20], weights=[35, 25, 15, 12, 7, 4, 2])[0]
                customer_id = rng.randint(1, len(CUSTOMERS))
                region_id = CUSTOMERS[customer_id - 1][3]
                rep_ids = [i + 1 for i, r in enumerate(REPS) if r[1] == region_id]
                rep_id = rng.choice(rep_ids) if rep_ids else rng.randint(1, len(REPS))
                rows.append(
                    (sale_date, customer_id, product_id, rep_id, quantity, price,
                     round(quantity * price, 2))
                )
            cur.executemany(
                """INSERT INTO sales (sale_date, customer_id, product_id, rep_id,
                                     quantity, unit_price, total_amount)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                rows,
            )
            cur.execute("SELECT COUNT(*), SUM(total_amount) FROM sales")
            count, total = cur.fetchone()
        print(f"Seeded {count} sales rows, total revenue Rs {total:,.2f}")
        print(f"  regions={len(REGIONS)} customers={len(CUSTOMERS)} "
              f"products={len(PRODUCTS)} reps={len(REPS)}")


if __name__ == "__main__":
    main()
