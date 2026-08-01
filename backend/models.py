"""Relational schema for the InsightFlow demo business."""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60), index=True)
    brand: Mapped[str] = mapped_column(String(60))
    unit_cost: Mapped[float] = mapped_column(Float)
    unit_price: Mapped[float] = mapped_column(Float)

    sales: Mapped[list["Sale"]] = relationship(back_populates="product")


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city: Mapped[str] = mapped_column(String(60))
    segment: Mapped[str] = mapped_column(String(60), index=True)
    lifetime_value: Mapped[float] = mapped_column(Float)

    sales: Mapped[list["Sale"]] = relationship(back_populates="customer")


class Sale(Base):
    __tablename__ = "sales"

    sale_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    region: Mapped[str] = mapped_column(String(60), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id"))
    quantity: Mapped[int] = mapped_column(Integer)
    revenue: Mapped[float] = mapped_column(Float)
    cost: Mapped[float] = mapped_column(Float)
    profit: Mapped[float] = mapped_column(Float)

    product: Mapped["Product"] = relationship(back_populates="sales")
    customer: Mapped["Customer"] = relationship(back_populates="sales")


class Inventory(Base):
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"))
    warehouse: Mapped[str] = mapped_column(String(60))
    stock_level: Mapped[int] = mapped_column(Integer)
    reorder_point: Mapped[int] = mapped_column(Integer)


class MarketingCampaign(Base):
    __tablename__ = "marketing_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_name: Mapped[str] = mapped_column(String(120))
    budget: Mapped[float] = mapped_column(Float)
    conversions: Mapped[int] = mapped_column(Integer)
    revenue_generated: Mapped[float] = mapped_column(Float)
