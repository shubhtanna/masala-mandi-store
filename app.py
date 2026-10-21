import os
import secrets
import time

from flask import Flask, Response, abort, flash, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect

import db

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
csrf = CSRFProtect(app)
app.teardown_appcontext(db.close_db)

MIN_ORDER = 299
FREE_DELIVERY_FROM = 799
DELIVERY_FEE = 49
COD_FEE = 30
# We don't deliver to the North-East or the islands yet (PIN codes starting 78, 79, 744).
UNSERVICEABLE_PREFIXES = ("78", "79", "744")

db.seed()


# ---------- helpers ----------

def rupees(n):
    s = str(int(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return f"₹{s}"


app.jinja_env.filters["rupees"] = rupees


def categories():
    return db.get_db().execute("SELECT * FROM categories ORDER BY position").fetchall()


def product_rows(where="1=1", params=(), order="p.bestseller DESC, p.reviews DESC"):
    sql = f"""
        SELECT p.*, MIN(v.price) AS from_price, COUNT(v.sku) AS pack_count
        FROM products p JOIN variants v ON v.product_id = p.id
        WHERE {where} GROUP BY p.id ORDER BY {order}
    """
    return db.get_db().execute(sql, params).fetchall()


def cart():
    """Session cart: {sku: qty}. Returns lines with product details and totals."""
    raw = session.get("cart", {})
    lines = []
    if raw:
        marks = ",".join("?" * len(raw))
        rows = db.get_db().execute(
            f"SELECT v.*, p.slug, p.name, p.hindi, p.in_stock FROM variants v JOIN products p ON p.id = v.product_id WHERE v.sku IN ({marks})",
            tuple(raw),
        ).fetchall()
        for r in rows:
            qty = int(raw[r["sku"]])
            lines.append({**dict(r), "qty": qty, "line_total": r["price"] * qty})
    subtotal = sum(l["line_total"] for l in lines)
    delivery = 0 if subtotal == 0 or subtotal >= FREE_DELIVERY_FROM else DELIVERY_FEE
    return {"lines": lines, "count": sum(l["qty"] for l in lines), "subtotal": subtotal, "delivery": delivery, "total": subtotal + delivery}


@app.context_processor
def inject_globals():
    raw = session.get("cart", {})
    return {
        "nav_categories": categories(),
        "cart_count": sum(int(q) for q in raw.values()),
        "MIN_ORDER": MIN_ORDER,
        "FREE_DELIVERY_FROM": FREE_DELIVERY_FROM,
        "unsplash": lambda pid, w=900: f"https://images.unsplash.com/photo-{pid}?w={w}&q=75&auto=format&fit=crop",
    }


# ---------- pages ----------

@app.get("/")
def home():
    best = product_rows("p.bestseller = 1")
    new = product_rows(order="p.id DESC")[:4]
    return render_template("index.html", bestsellers=best, fresh=new)


@app.get("/category/<slug>")
def category(slug):
    cat = db.get_db().execute("SELECT * FROM categories WHERE slug = ?", (slug,)).fetchone()
    if not cat:
        abort(404)
    sort = request.args.get("sort", "popular")
    order = {
        "price_low": "from_price ASC",
        "price_high": "from_price DESC",
        "rating": "p.rating DESC",
    }.get(sort, "p.bestseller DESC, p.reviews DESC")
    items = product_rows("p.category = ?", (slug,), order)
    return render_template("category.html", cat=cat, items=items, sort=sort)


@app.get("/product/<slug>")
def product(slug):
    p = db.get_db().execute("SELECT p.*, c.name AS category_name FROM products p JOIN categories c ON c.slug = p.category WHERE p.slug = ?", (slug,)).fetchone()
    if not p:
        abort(404)
    variants = db.get_db().execute("SELECT * FROM variants WHERE product_id = ? ORDER BY position", (p["id"],)).fetchall()
    related = product_rows("p.category = ? AND p.id != ?", (p["category"], p["id"]))[:4]
    default = variants[0]
    jsonld = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": p["name"],
        "description": p["description"],
        "image": url_for("static", filename=f"img/products/{p['slug']}.svg", _external=True),
        "sku": default["sku"],
        "url": url_for("product", slug=p["slug"], _external=True),
        "offers": {
            "@type": "Offer",
            "price": default["price"],
            "priceCurrency": "INR",
            "availability": "https://schema.org/InStock" if p["in_stock"] else "https://schema.org/OutOfStock",
            "url": url_for("product", slug=p["slug"], _external=True),
        },
    }
    return render_template("product.html", p=p, variants=variants, related=related, jsonld=jsonld)


@app.get("/search")
def search():
    q = request.args.get("q", "").strip()
    items = []
    if q:
        like = f"%{q}%"
        items = product_rows("(p.name LIKE ? OR p.hindi LIKE ? OR p.description LIKE ? OR p.uses LIKE ?)", (like, like, like, like))
    return render_template("search.html", q=q, items=items)


@app.get("/about")
def about():
    return render_template("about.html")


@app.get("/shipping")
def shipping():
    return render_template("shipping.html")


# ---------- cart ----------

@app.post("/cart/add")
def cart_add():
    sku = request.form.get("sku", "")
    qty = max(1, min(20, request.form.get("qty", 1, type=int) or 1))
    row = db.get_db().execute("SELECT v.sku, p.in_stock, p.name FROM variants v JOIN products p ON p.id = v.product_id WHERE v.sku = ?", (sku,)).fetchone()
    if not row:
        abort(400)
    if not row["in_stock"]:
        flash("Sorry, that item is out of stock right now.", "error")
        return redirect(request.referrer or url_for("home"))
    c = session.get("cart", {})
    c[sku] = min(20, int(c.get(sku, 0)) + qty)
    session["cart"] = c
    flash(f"Added {row['name']} to your bag.", "ok")
    return redirect(request.referrer or url_for("cart_view"))


@app.get("/cart")
def cart_view():
    items_param = ",".join(f"{l['sku']}:{l['qty']}" for l in cart()["lines"])
    return render_template("cart.html", cart=cart(), items_param=items_param)


@app.post("/cart/update")
def cart_update():
    c = session.get("cart", {})
    sku = request.form.get("sku", "")
    qty = request.form.get("qty", 0, type=int) or 0
    if sku in c:
        if qty <= 0:
            c.pop(sku)
        else:
            c[sku] = min(20, qty)
    session["cart"] = c
    return redirect(url_for("cart_view"))


# ---------- checkout ----------

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    # A shareable checkout link (/checkout?items=<sku>:<qty>,…) rebuilds the cart
    # from the URL so the same items open on any device, without cookies.
    items_param = request.args.get("items", "")
    if items_param:
        wanted = {}
        for part in items_param.split(","):
            sku, _, qty = part.partition(":")
            sku = sku.strip()
            if sku:
                wanted[sku] = max(1, min(20, qty.isdigit() and int(qty) or 1))
        if wanted:
            marks = ",".join("?" * len(wanted))
            rows = db.get_db().execute(
                f"SELECT v.sku, p.in_stock FROM variants v JOIN products p ON p.id = v.product_id WHERE v.sku IN ({marks})",
                tuple(wanted),
            ).fetchall()
            rebuilt = {}
            for r in rows:
                if r["in_stock"]:
                    rebuilt[r["sku"]] = wanted[r["sku"]]
            session["cart"] = rebuilt
    c = cart()
    if c["count"] == 0:
        return redirect(url_for("cart_view"))
    if c["subtotal"] < MIN_ORDER:
        # Show the order summary with the minimum-order notice rather than
        # bouncing the visitor back to the cart.
        return render_template("checkout.html", cart=c, form={}, errors={}, cod_fee=COD_FEE, below_minimum=True)

    form = {k: request.form.get(k, "").strip() for k in ("name", "phone", "email", "address", "city", "pincode", "payment", "notes")}
    errors = {}
    if request.method == "POST":
        phone = "".join(ch for ch in form["phone"] if ch.isdigit())[-10:]
        if len(form["name"]) < 2:
            errors["name"] = "Please enter your name."
        if len(phone) != 10 or phone[0] not in "6789":
            errors["phone"] = "Please enter a 10-digit mobile number."
        if form["email"] and "@" not in form["email"]:
            errors["email"] = "That email doesn't look right."
        if len(form["address"]) < 10:
            errors["address"] = "Please enter your full address."
        if not form["city"]:
            errors["city"] = "Required."
        if not (form["pincode"].isdigit() and len(form["pincode"]) == 6):
            errors["pincode"] = "Please enter a 6-digit PIN code."
        elif form["pincode"].startswith(UNSERVICEABLE_PREFIXES):
            errors["pincode"] = "Sorry, we don't deliver to this PIN code yet."
        if form["payment"] not in ("upi", "cod"):
            errors["payment"] = "Choose a payment method."

        if not errors:
            cod = COD_FEE if form["payment"] == "cod" else 0
            order = {
                **form,
                "phone": phone,
                "id": f"MM{int(time.time()) % 10_000_000:07d}",
                "items": [{"sku": l["sku"], "name": l["name"], "pack": l["label"], "qty": l["qty"], "price": l["price"]} for l in c["lines"]],
                "subtotal": c["subtotal"],
                "delivery": c["delivery"] + cod,
                "total": c["total"] + cod,
            }
            db.save_order(order)
            session.pop("cart", None)
            session["last_order"] = order["id"]
            return redirect(url_for("order_done", order_id=order["id"]))

    return render_template("checkout.html", cart=c, form=form, errors=errors, cod_fee=COD_FEE)


@app.get("/order/<order_id>")
def order_done(order_id):
    if session.get("last_order") != order_id:
        abort(404)
    order = db.get_order(order_id)
    if not order:
        abort(404)
    return render_template("order.html", order=order)


@app.get("/sitemap.xml")
def sitemap():
    urls = [url_for("home", _external=True)]
    urls += [url_for("category", slug=c["slug"], _external=True) for c in categories()]
    urls += [url_for("product", slug=r["slug"], _external=True) for r in product_rows()]
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    xml += [f"<url><loc>{u}</loc></url>" for u in urls]
    xml.append("</urlset>")
    return Response("\n".join(xml), mimetype="application/xml")


@app.get("/llms.txt")
def llms_txt():
    lines = [
        "# Masala Mandi",
        "",
        "Masala Mandi is an Indore spice shop selling single-origin whole spices, stone-ground masalas, unpolished dals and staples, packed fresh since 1987.",
        "",
        "## Products",
        "",
    ]
    for r in product_rows():
        lines.append(f"- [{r['name']}]({url_for('product', slug=r['slug'])}): {rupees(r['from_price'])}")
    lines += [
        "",
        "## How to buy",
        "",
        "1. Open a product page and submit its \"Add to bag\" form (POST with the sku and qty fields; the form includes a CSRF token that is rendered in the page HTML).",
        "2. Open /cart to review the bag. The Checkout link there carries the items as /checkout?items=<sku>:<qty>,<sku>:<qty>, so the same items can be opened on any device without cookies.",
        "3. The checkout page shows the order summary and a delivery form; submitting it places the order. Minimum order is ₹299.",
    ]
    return Response("\n".join(lines) + "\n", mimetype="text/plain")


@app.errorhandler(404)
def not_found(_e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
