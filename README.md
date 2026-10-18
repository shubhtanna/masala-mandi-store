# Masala Mandi

Online shop for Masala Mandi, a spice and grocery business from Indore: whole and ground spices, masala blends, dals, rice, atta and tea.

> This is a demo store. No real orders, payments or deliveries are processed.

Flask 3, Jinja templates, SQLite and plain CSS. Works without JavaScript.

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000. The SQLite database (`mandi.db`) is created and seeded from `catalog.py` on start-up.

## Production

```bash
gunicorn app:app
```

Set `SECRET_KEY` in the environment (sessions and CSRF tokens depend on it). Hosted on Render.

## Notes

- `catalog.py`: categories and products; each pack size is its own SKU (`MM-013-100` = product 13, 100 g)
- Cart lives in the signed Flask session; all forms are CSRF-protected (Flask-WTF)
- Minimum order ₹299, free delivery from ₹799, no delivery yet to PIN codes starting 78, 79 or 744
- Orders are saved to the `orders` table

Category photos from [Unsplash](https://unsplash.com).
