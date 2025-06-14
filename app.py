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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                   (user_id, phone_hash, country, language, 0, datetime.now(timezone.utc)))
    conn.commit()
    conn.close()
    return user_id
def add_points_to_user(phone_number, points=1):
    phone_hash = hash_phone_number(phone_number)
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET points = points + ? WHERE phone_hash = ?", (points, phone_hash))
    cursor.execute("SELECT points FROM users WHERE phone_hash = ?", (phone_hash,))
    new_points = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return new_points

def corriger_message(msg):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Corrige les fautes de frappe et de grammaire sans changer le sens du message."},
                {"role": "user", "content": msg}
            ],
            max_tokens=100
        )
        return response.choices[0].message["content"]
    except Exception:
        return msg

def search_hotels(city):
    hotels = [f"{city} Palace", f"Riad {city} Medina", f"Dar Atlas {city}", f"Luxury Stay {city}", f"Hotel Central {city}"]
    return "\n".join([f"🏨 Hôtels à {city} :"] + [f"{i+1}. {h}" for i, h in enumerate(hotels)])

def search_restaurants(city, cuisine=None):
    if cuisine:
        return f"🍽️ Restaurants {cuisine} à {city} :\n1. Saveurs {cuisine}\n2. Chez {cuisine} House\n3. Délices de {cuisine}"
    return f"🍽️ Restaurants populaires à {city} :\n1. La Table\n2. Resto Bahia\n3. Café du Coin"

def search_flights(origin, destination):
    return f"✈️ Vols de {origin} à {destination} :\n1. RAM - 08h00\n2. Air Arabia - 13h30\n3. EasyJet - 18h45"

def generate_baggage_claim():
    return "📄 Réclamation :\nMon bagage a été perdu/endommagé. Merci de traiter cette demande dès que possible."

def generate_travel_plan(city):
    return f"🗺️ Plan de voyage à {city} :\n- Jour 1 : visites culturelles\n- Jour 2 : activités locales\n- Jour 3 : gastronomie"

def get_travel_deals(country):
    return f"💡 Bons plans au {country} :\n- Réductions hôtels\n- Marchés locaux\n- Transports à prix réduit\n- Tours guidés"
@app.route("/webhook/whatsapp-webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    phone_number = request.values.get("From", "").replace("whatsapp:", "")
    country = request.values.get("WaId", "")[:2] if request.values.get("WaId") else "unknown"
    language = "auto"

    create_user_profile(phone_number, country, language)

    corrected_msg = corriger_message(incoming_msg)
    msg_lower = corrected_msg.lower()

    # Affichage du profil utilisateur
    if "mon profil" in msg_lower or "mes points" in msg_lower:
        phone_hash = hash_phone_number(phone_number)
        conn = sqlite3.connect("askely.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, points, created_at FROM users WHERE phone_hash = ?", (phone_hash,))
        data = cursor.fetchone()
        conn.close()

        if data:
            user_id, points, created_at = data
            msg = f"👤 *Votre Profil Askely*\n🆔 ID : {user_id}\n⭐ Points : {points}\n📅 Inscrit le : {created_at[:10]}"
        else:
            msg = "Profil introuvable. Avez-vous déjà utilisé Askely ?"

        resp = MessagingResponse()
        resp.message(msg)
        return str(resp)

    # Hôtels
    match_hotel = re.search(r"h[oô]tel(?: à| a)? ([\w\s\-]+)", msg_lower)
    if match_hotel:
        city = match_hotel.group(1).strip().title()
        result = search_hotels(city)
        points = add_points_to_user(phone_number, 1)
        resp = MessagingResponse()
        resp.message(f"{result}\n🎁 Vous gagnez 1 point Askely ! Total : {points} ⭐️\n📌 Tapez *mon profil* pour consulter vos points.")
        return str(resp)
    # Restaurants
    match_restaurant = re.search(r"restaurant(?: [\w]+)?(?: à| a)? ([\w\s\-]+)", msg_lower)
    if match_restaurant:
        city = match_restaurant.group(1).strip().title()
        result = search_restaurants(city)
        points = add_points_to_user(phone_number, 1)
        resp = MessagingResponse()
        resp.message(f"{result}\n🎁 Vous gagnez 1 point Askely ! Total : {points} ⭐️\n📌 Tapez *mon profil* pour consulter vos points.")
        return str(resp)

    # Vols
    match_flight = re.search(r"vol(?: de)? ([\w\s]+) vers ([\w\s]+)", msg_lower)
    if match_flight:
        origin = match_flight.group(1).strip().title()
        destination = match_flight.group(2).strip().title()
        result = search_flights(origin, destination)
        points = add_points_to_user(phone_number, 1)
        resp = MessagingResponse()
        resp.message(f"{result}\n🎁 Vous gagnez 1 point Askely ! Total : {points} ⭐️\n📌 Tapez *mon profil* pour consulter vos points.")
        return str(resp)

    # Réclamations bagage
    if "bagage" in msg_lower or "réclamation" in msg_lower:
        result = generate_baggage_claim()
        points = add_points_to_user(phone_number, 2)
        resp = MessagingResponse()
        resp.message(f"{result}\n🎁 Vous gagnez 2 points Askely ! Total : {points} ⭐️\n📌 Tapez *mon profil* pour consulter vos points.")
        return str(resp)

    # Plan de voyage
    match_plan = re.search(r"(plan|itinéraire)(?: à| pour)? ([\w\s\-]+)", msg_lower)
    if match_plan:
        city = match_plan.group(2).strip().title()
        result = generate_travel_plan(city)
        points = add_points_to_user(phone_number, 2)
        resp = MessagingResponse()
        resp.message(f"{result}\n🎁 Vous gagnez 2 points Askely ! Total : {points} ⭐️\n📌 Tapez *mon profil* pour consulter vos points.")
        return str(resp)

    # Bons plans
    match_deal = re.search(r"bons? plans? (?:au|en|dans le)? ([\w\s\-]+)", msg_lower)
    if match_deal:
        country = match_deal.group(1).strip().title()
        result = get_travel_deals(country)
        points = add_points_to_user(phone_number, 1)
        resp = MessagingResponse()
        resp.message(f"{result}\n🎁 Vous gagnez 1 point Askely ! Total : {points} ⭐️\n📌 Tapez *mon profil* pour consulter vos points.")
        return str(resp)

    # Réponse par défaut via GPT
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Tu es Askely, un assistant de voyage intelligent, multilingue et très serviable."},
                {"role": "user", "content": corrected_msg}
            ],
            max_tokens=300
        )
        answer = response.choices[0].message["content"]
    except Exception:
        answer = "❌ Erreur avec l'intelligence artificielle. Veuillez réessayer."

    points = add_points_to_user(phone_number, 1)
    resp = MessagingResponse()
    resp.message(f"{answer}\n🎁 Vous gagnez 1 point Askely ! Total : {points} ⭐️\n📌 Tapez *mon profil* pour consulter vos points.")
    return str(resp)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
