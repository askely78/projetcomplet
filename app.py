from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import openai
import os
import hashlib
import uuid
import sqlite3
from datetime import datetime
import re

app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")

# Initialisation de la base de données
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# Hash sécurisé du numéro de téléphone
def hash_phone_number(phone_number):
    return hashlib.sha256(phone_number.encode()).hexdigest()

# Création de profil utilisateur sécurisé
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
    cursor.execute("""
        INSERT INTO users (id, phone_hash, country, language, points, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, phone_hash, country, language, 0, datetime.utcnow()))
    conn.commit()
    conn.close()
    return user_id

# Fonctions de service simulées
def search_hotels(city):
    return f"🏨 Hôtels populaires à {city} :\n1. Atlas Hotel\n2. Riad Medina\n3. Comfort Inn {city}"

def search_restaurants(city, cuisine=None):
    if cuisine:
        return f"🍽️ Restaurants {cuisine} à {city} :\n1. {cuisine} Palace\n2. Saveurs de {cuisine}\n3. Restaurant Medina"
    return f"🍽️ Restaurants populaires à {city} :\n1. Le Gourmet\n2. Resto Bahia\n3. Café du Coin"

def search_flights(origin, destination):
    return f"✈️ Vols de {origin} vers {destination} :\n1. Air Maroc - 08h45\n2. Ryanair - 12h15\n3. Transavia - 18h30"

# Webhook WhatsApp
@app.route("/webhook/whatsapp-webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    phone_number = request.values.get("From", "").replace("whatsapp:", "")
    country = request.values.get("WaId", "")[:2] if request.values.get("WaId") else "unknown"
    language = "auto"
    user_id = create_user_profile(phone_number, country, language)

    msg_lower = incoming_msg.lower()

    # Recherche hôtel
    match_hotel = re.search(r"h[oô]tel(?: à| a)? ([\w\s\-]+)", msg_lower)
    if match_hotel:
        city = match_hotel.group(1).strip().title()
        result = search_hotels(city)
        resp = MessagingResponse()
        resp.message(f"[ID : {user_id}]\n{result}")
        return str(resp)

    # Recherche restaurant
    match_restaurant = re.search(r"restaurant(?: [\w]+)?(?: à| a)? ([\w\s\-]+)", msg_lower)
    if match_restaurant:
        city = match_restaurant.group(1).strip().title()
        result = search_restaurants(city)
        resp = MessagingResponse()
        resp.message(f"[ID : {user_id}]\n{result}")
        return str(resp)

    # Recherche vol
    match_flight = re.search(r"vol(?: de)? ([\w\s]+) vers ([\w\s]+)", msg_lower)
    if match_flight:
        origin = match_flight.group(1).strip().title()
        destination = match_flight.group(2).strip().title()
        result = search_flights(origin, destination)
        resp = MessagingResponse()
        resp.message(f"[ID : {user_id}]\n{result}")
        return str(resp)

    # Sinon appel GPT
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Tu es Askely, un assistant de voyage intelligent, multilingue et serviable."},
                {"role": "user", "content": incoming_msg}
            ],
            max_tokens=300
        )
        answer = response.choices[0].message["content"]
    except Exception:
        answer = "❌ Erreur avec l'intelligence artificielle. Veuillez réessayer."

    resp = MessagingResponse()
    resp.message(f"[ID : {user_id}]\n{answer}")
    return str(resp)

# Lancement compatible Render
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
