from flask import Flask, request, render_template_string
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
    cursor.execute("INSERT INTO users (id, phone_hash, country, language, points, created_at) VALUES (?, ?, ?, ?, ?, ?)", (user_id, phone_hash, country, language, 0, datetime.now(timezone.utc)))
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
                {"role": "system", "content": "Corrige les fautes de frappe et de grammaire dans ce message sans changer son sens."},
                {"role": "user", "content": msg}
            ],
            max_tokens=100
        )
        return response.choices[0].message["content"]
    except Exception:
        return msg

def search_hotels(city):
    hotels = [f"{city} Palace Hotel", f"Riad {city} Medina", f"Comfort Inn {city}", f"Dar Atlas {city}", f"Luxury Stay {city}"]
    return "\n".join([f"🏨 Hôtels recommandés à {city} :"] + [f"{i+1}. {h}" for i, h in enumerate(hotels)])

def search_restaurants(city, cuisine=None):
    if cuisine:
        return f"🍽️ Restaurants {cuisine} à {city} :\n1. {cuisine} Palace\n2. Saveurs de {cuisine}\n3. Restaurant Medina"
    return f"🍽️ Restaurants populaires à {city} :\n1. Le Gourmet\n2. Resto Bahia\n3. Café du Coin"

def search_flights(origin, destination):
    return f"✈️ Vols de {origin} vers {destination} :\n1. Air Maroc - 08h45\n2. Ryanair - 12h15\n3. Transavia - 18h30"

def generate_baggage_claim():
    return "📄 Réclamation bagage :\nMadame, Monsieur,\nSuite à mon vol, mon bagage a été perdu/endommagé.\nMerci de traiter cette réclamation.\nCordialement."

def generate_travel_plan(city):
    return f"🗺️ Plan de voyage à {city} sur 3 jours :\n- Jour 1 : Médina\n- Jour 2 : Musées et jardins\n- Jour 3 : Gastronomie et détente"

def get_travel_deals(country):
    return f"💡 Bons plans au {country} :\n- Réductions hôtels\n- Entrées musées\n- Marchés artisanaux\n- Carte SIM locale"

@app.route("/webhook/whatsapp-webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    phone_number = request.values.get("From", "").replace("whatsapp:", "")
    country = request.values.get("WaId", "")[:2] if request.values.get("WaId") else "unknown"
    language = "auto"
    create_user_profile(phone_number, country, language)

    corrected_msg = corriger_message(incoming_msg)
    msg_lower = corrected_msg.lower()

    if "mon profil" in msg_lower or "mes points" in msg_lower:
        profil_url = f"https://projetcomplet.onrender.com/profil?tel={phone_number}"
        points = add_points_to_user(phone_number, 0)
        resp = MessagingResponse()
        resp.message(f"👤 Voici votre profil Askely :\n{profil_url}\n\nVous avez actuellement ⭐ {points} points.")
        return str(resp)

    match_hotel = re.search(r"h[oô]tel(?: à| a)? ([\w\s\-]+)", msg_lower)
    if match_hotel:
        city = match_hotel.group(1).strip().title()
        result = search_hotels(city)
        points = add_points_to_user(phone_number, 1)
        resp = MessagingResponse()
        resp.message(f"{result}\n🎁 Vous gagnez 1 point Askely ! Total : {points} ⭐️")
        return str(resp)

    match_restaurant = re.search(r"restaurant(?: [\w]+)?(?: à| a)? ([\w\s\-]+)", msg_lower)
    if match_restaurant:
        city = match_restaurant.group(1).strip().title()
        result = search_restaurants(city)
        points = add_points_to_user(phone_number, 1)
        resp = MessagingResponse()
        resp.message(f"{result}\n🎁 Vous gagnez 1 point Askely ! Total : {points} ⭐️")
        return str(resp)

    match_flight = re.search(r"vol(?: de)? ([\w\s]+) vers ([\w\s]+)", msg_lower)
    if match_flight:
        origin = match_flight.group(1).strip().title()
        destination = match_flight.group(2).strip().title()
        result = search_flights(origin, destination)
        points = add_points_to_user(phone_number, 1)
        resp = MessagingResponse()
        resp.message(f"{result}\n🎁 Vous gagnez 1 point Askely ! Total : {points} ⭐️")
        return str(resp)

    if "bagage" in msg_lower or "réclamation" in msg_lower:
        result = generate_baggage_claim()
        points = add_points_to_user(phone_number, 2)
        resp = MessagingResponse()
        resp.message(f"{result}\n🎁 Vous gagnez 2 points Askely ! Total : {points} ⭐️")
        return str(resp)

    match_plan = re.search(r"(plan|itinéraire)(?: à| pour)? ([\w\s\-]+)", msg_lower)
    if match_plan:
        city = match_plan.group(2).strip().title()
        result = generate_travel_plan(city)
        points = add_points_to_user(phone_number, 2)
        resp = MessagingResponse()
        resp.message(f"{result}\n🎁 Vous gagnez 2 points Askely ! Total : {points} ⭐️")
        return str(resp)

    match_deal = re.search(r"bons? plans? (?:au|en|dans le)? ([\w\s\-]+)", msg_lower)
    if match_deal:
        country = match_deal.group(1).strip().title()
        result = get_travel_deals(country)
        points = add_points_to_user(phone_number, 1)
        resp = MessagingResponse()
        resp.message(f"{result}\n🎁 Vous gagnez 1 point Askely ! Total : {points} ⭐️")
        return str(resp)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Tu es Askely, un assistant de voyage intelligent, multilingue et serviable."},
                {"role": "user", "content": corrected_msg}
            ],
            max_tokens=300
        )
        answer = response.choices[0].message["content"]
    except Exception:
        answer = "❌ Erreur avec l'intelligence artificielle. Veuillez réessayer."

    points = add_points_to_user(phone_number, 1)
    resp = MessagingResponse()
    resp.message(f"{answer}\n🎁 Vous gagnez 1 point Askely ! Total : {points} ⭐️")
    return str(resp)

@app.route("/profil")
def afficher_profil():
    tel = request.args.get("tel")
    if not tel:
        return "❌ Veuillez fournir ?tel=NUMÉRO", 400

    phone_hash = hash_phone_number(tel)
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, points, created_at FROM users WHERE phone_hash = ?", (phone_hash,))
    data = cursor.fetchone()
    conn.close()

    if not data:
        return "❌ Utilisateur introuvable. Avez-vous utilisé Askely sur WhatsApp ?"

    user_id, points, created_at = data

    html = f"""
    <html><head><title>Profil Askely</title></head>
    <body style='font-family:sans-serif; text-align:center; padding:30px;'>
        <h2>👤 Mon Profil Askely</h2>
        <p><strong>ID :</strong> {user_id}</p>
        <p><strong>Points :</strong> ⭐ {points} points</p>
        <p><strong>Inscrit le :</strong> {created_at}</p>
    </body></html>
    """
    return render_template_string(html)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
