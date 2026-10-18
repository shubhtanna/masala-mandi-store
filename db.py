"""SQLite storage. The catalogue is (re)seeded from catalog.py on start-up."""

import json
import sqlite3
from pathlib import Path

from flask import g

DB_PATH = Path(__file__).with_name("mandi.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    slug TEXT PRIMARY KEY, name TEXT, hindi TEXT, blurb TEXT, photo TEXT, position INTEGER
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY, slug TEXT UNIQUE, name TEXT, hindi TEXT, category TEXT, origin TEXT,
    description TEXT, uses TEXT, rating REAL, reviews INTEGER, in_stock INTEGER, bestseller INTEGER
);
CREATE TABLE IF NOT EXISTS variants (
    sku TEXT PRIMARY KEY, product_id INTEGER, label TEXT, grams INTEGER, price INTEGER, position INTEGER
);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, name TEXT, phone TEXT, email TEXT,
    address TEXT, city TEXT, pincode TEXT, payment TEXT, notes TEXT, items TEXT, subtotal INTEGER,
    delivery INTEGER, total INTEGER
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def seed():
    from catalog import BESTSELLERS, CATEGORIES, PRODUCTS

    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)
    db.execute("DELETE FROM categories")
    db.execute("DELETE FROM variants")
    db.execute("DELETE FROM products")
    for i, c in enumerate(CATEGORIES):
        db.execute("INSERT INTO categories VALUES (?,?,?,?,?,?)", (c["slug"], c["name"], c["hindi"], c["blurb"], c["photo"], i))
    for pid, p in enumerate(PRODUCTS, 1):
        db.execute(
            "INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, p["slug"], p["name"], p["hindi"], p["category"], p["origin"], p["description"], p["uses"],
             p["rating"], p["reviews"], int(p["stock"]), int(p["slug"] in BESTSELLERS)),
        )
        for pos, (suffix, label, grams, price) in enumerate(p["packs"]):
            db.execute("INSERT INTO variants VALUES (?,?,?,?,?,?)", (f"MM-{pid:03d}-{suffix}", pid, label, grams, price, pos))
    db.commit()
    db.close()


def save_order(order):
    db = get_db()
    db.execute(
        "INSERT INTO orders (id,name,phone,email,address,city,pincode,payment,notes,items,subtotal,delivery,total) "
        "VALUES (:id,:name,:phone,:email,:address,:city,:pincode,:payment,:notes,:items,:subtotal,:delivery,:total)",
        {**order, "items": json.dumps(order["items"])},
    )
    db.commit()


def get_order(order_id):
    row = get_db().execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        return None
    order = dict(row)
    order["items"] = json.loads(order["items"])
    return order
