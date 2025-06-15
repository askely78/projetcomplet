
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import openai
import os
import hashlib
import uuid
import sqlite3
from datetime import datetime, timezone
import re

app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")

def init_db():
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            phone_hash TEXT UNIQUE,
            country TEXT,
            language TEXT,
            points INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_hash TEXT,
            type TEXT,
            rating INTEGER,
            comment TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def hash_phone_number(phone_number):
    return hashlib.sha256(phone_number.encode()).hexdigest()

def create_user_profile(phone_number, country="unknown", language="unknown"):
    phone_hash = hash_phone_number(phone_number)
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE phone_hash = ?", (phone_hash,))
    existing_user = cursor.fetchone()
    if existing_user:
        conn.close()
        return existing_user[0]
    user_id = f"askely_{uuid.uuid4().hex[:8]}"
    cursor.execute("INSERT INTO users (id, phone_hash, country, language, points, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                   (user_id, phone_hash, country, language, 0, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()
    return user_id

def add_points(phone_hash, amount):
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET points = points + ? WHERE phone_hash = ?", (amount, phone_hash))
    cursor.execute("SELECT points FROM users WHERE phone_hash = ?", (phone_hash,))
    points = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return points

def save_review(phone_hash, review_type, rating, comment):
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO reviews (phone_hash, type, rating, comment) VALUES (?, ?, ?, ?)",
                   (phone_hash, review_type, rating, comment))
    conn.commit()
    conn.close()

def get_last_reviews(phone_hash, n=3):
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("SELECT type, rating, comment FROM reviews WHERE phone_hash = ? ORDER BY created_at DESC LIMIT ?", (phone_hash, n))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_public_reviews(n=5):
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("SELECT type, rating, comment FROM reviews ORDER BY created_at DESC LIMIT ?", (n,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def corriger_message(msg):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Corrige les fautes sans changer le sens."},
                {"role": "user", "content": msg}
            ],
            max_tokens=100
        )
        return response.choices[0].message["content"]
    except Exception:
        return msg

def search_hotels(city):
    hotels = [f"{city} Palace", f"Riad {city}", f"Dar Atlas {city}", f"Luxury Stay {city}", f"Hotel Central {city}"]
    return "\n".join([f"🏨 Hôtels à {city} :"] + [f"{i+1}. {h}" for i, h in enumerate(hotels)])

def search_restaurants(city):
    restos = [f"{city} Gourmet", f"Bistro {city}", f"Chez {city}", f"La Table {city}", f"Café Medina"]
    return "\n".join([f"🍽️ Restaurants à {city} :"] + [f"{i+1}. {r}" for i, r in enumerate(restos)])

def search_flights(origin, destination):
    return f"✈️ Vols de {origin} à {destination} :\n1. RAM 08h00\n2. Air Arabia 13h30\n3. Transavia 19h00"

def generate_travel_plan(city):
    return f"🗺️ Circuit touristique à {city} :\n- Jour 1 : visite guidée\n- Jour 2 : cuisine locale\n- Jour 3 : détente & shopping"

def get_travel_deals(country):
    return f"💡 Bons plans au {country} :\n- Réductions hébergement\n- Activités gratuites\n- Transports locaux pas chers"


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
