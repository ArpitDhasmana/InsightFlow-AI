"""Generate realistic demo data for the InsightFlow business.

Run with:  python -m backend.seed_data
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from .database import Base, SessionLocal, engine
from .models import Customer, Inventory, MarketingCampaign, Product, Sale

REGIONS = ["North America", "Europe", "Asia Pacific", "Latin America"]
CITIES = ["Seattle", "London", "Singapore", "Berlin", "Toronto", "Sydney", "Austin"]
SEGMENTS = ["Enterprise", "Mid-Market", "SMB", "Consumer"]
WAREHOUSES = ["WH-East", "WH-West", "WH-Central"]

PRODUCTS = [
    ("Aurora Analytics Suite", "Software", "InsightFlow", 40, 199),
    ("Nimbus Cloud Storage", "Software", "InsightFlow", 12, 59),
    ("Pulse CRM", "Software", "Vertex", 55, 249),
    ("Forge Data Warehouse", "Software", "Vertex", 120, 499),
    ("Beacon BI Dashboard", "Software", "InsightFlow", 30, 149),
    ("Sentinel Security", "Software", "Aegis", 70, 299),
    ("Relay Messaging", "Software", "Aegis", 8, 39),
    ("Atlas ERP", "Software", "Vertex", 200, 799),
]


def _daterange(days: int):
    start = date.today() - timedelta(days=days)
    for i in range(days):
        yield start + timedelta(days=i)


def seed(days: int = 540, seed_value: int = 42) -> None:
    random.seed(seed_value)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    session = SessionLocal()
    try:
        products = [
            Product(
                product_id=i + 1,
                product_name=name,
                category=cat,
                brand=brand,
                unit_cost=cost,
                unit_price=price,
            )
            for i, (name, cat, brand, cost, price) in enumerate(PRODUCTS)
        ]
        session.add_all(products)

        customers = [
            Customer(
                customer_id=i + 1,
                city=random.choice(CITIES),
                segment=random.choice(SEGMENTS),
                lifetime_value=round(random.uniform(500, 50000), 2),
            )
            for i in range(120)
        ]
        session.add_all(customers)
        session.flush()

        sale_id = 1
        sales: list[Sale] = []
        for day in _daterange(days):
            # Gentle upward trend + weekly seasonality.
            day_index = (day - (date.today() - timedelta(days=days))).days
            trend = 1.0 + day_index / days * 0.6
            weekend = 0.7 if day.weekday() >= 5 else 1.0
            daily_orders = int(random.uniform(8, 18) * trend * weekend)

            for _ in range(daily_orders):
                product = random.choice(products)
                customer = random.choice(customers)
                qty = random.randint(1, 6)
                revenue = round(product.unit_price * qty, 2)
                cost = round(product.unit_cost * qty, 2)
                sales.append(
                    Sale(
                        sale_id=sale_id,
                        date=day,
                        region=random.choice(REGIONS),
                        product_id=product.product_id,
                        customer_id=customer.customer_id,
                        quantity=qty,
                        revenue=revenue,
                        cost=cost,
                        profit=round(revenue - cost, 2),
                    )
                )
                sale_id += 1
        session.add_all(sales)

        inventory = [
            Inventory(
                product_id=p.product_id,
                warehouse=random.choice(WAREHOUSES),
                stock_level=random.randint(0, 500),
                reorder_point=random.randint(50, 150),
            )
            for p in products
        ]
        session.add_all(inventory)

        campaigns = [
            MarketingCampaign(
                campaign_name=name,
                budget=budget,
                conversions=conv,
                revenue_generated=rev,
            )
            for name, budget, conv, rev in [
                ("Spring Launch", 50000, 820, 320000),
                ("Summer Growth", 75000, 1150, 610000),
                ("Enterprise Push", 120000, 430, 980000),
                ("Retargeting Q3", 30000, 640, 210000),
            ]
        ]
        session.add_all(campaigns)

        session.commit()
        print(f"Seeded {len(sales)} sales, {len(products)} products, {len(customers)} customers.")
    finally:
        session.close()


if __name__ == "__main__":
    seed()
