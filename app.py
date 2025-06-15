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
    if cursor.fetchone() is None:
        user_id = f"askely_{uuid.uuid4().hex[:8]}"
        cursor.execute("INSERT INTO users (id, phone_hash, country, language) VALUES (?, ?, ?, ?)",
                       (user_id, phone_hash, country, language))
        conn.commit()
    conn.close()
    return phone_hash

def add_points(phone_hash, amount):
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET points = points + ? WHERE phone_hash = ?", (amount, phone_hash))
    conn.commit()
    cursor.execute("SELECT points FROM users WHERE phone_hash = ?", (phone_hash,))
    points = cursor.fetchone()[0]
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
    return f"✈️ Vols de {origin} vers {destination} :\n1. RAM 08h00\n2. Air Arabia 13h30\n3. Transavia 19h00"

def generate_travel_plan(city):
    return f"🗺️ Circuit touristique à {city} :\n- Jour 1 : visite guidée\n- Jour 2 : cuisine locale\n- Jour 3 : détente & shopping"

def get_travel_deals(country):
    return f"💡 Bons plans au {country} :\n- Réductions hébergement\n- Activités gratuites\n- Transports locaux pas chers"

def get_main_menu():
    return (
        "🤖 *Bienvenue sur Askely* – Votre concierge intelligent 🌍\n\n"
        "Voici ce que vous pouvez faire 👇\n"
        "🏨 *Hôtel à [ville]*\n"
        "🍽️ *Restaurant à [ville]*\n"
        "✈️ *Vol de [ville A] vers [ville B]*\n"
        "🧳 *Réclamation bagage*\n"
        "🗺️ *Plan à [ville]*\n"
        "💡 *Bons plans au [pays]*\n"
        "⭐ *Évaluer vol/hôtel/restaurant/fidélité*\n"
        "📋 *Voir tous les avis*\n"
        "👤 *Mon profil*\n"
        "📌 Tapez *menu* à tout moment pour revoir ce menu"
    )

@app.route("/webhook/whatsapp-webhook", methods=["POST"])
def webhook():
    msg = request.values.get("Body", "").strip()
    phone = request.values.get("From", "").replace("whatsapp:", "")
    phone_hash = create_user_profile(phone)
    msg_corrigé = corriger_message(msg)
    msg_lower = msg_corrigé.lower()

    resp = MessagingResponse()

    if msg_lower in ["menu", "help", "aide"]:
        resp.message(get_main_menu())
        return str(resp)

    if "mon profil" in msg_lower:
        conn = sqlite3.connect("askely.db")
        cursor = conn.cursor()
        cursor.execute("SELECT points, created_at FROM users WHERE phone_hash = ?", (phone_hash,))
        data = cursor.fetchone()
        conn.close()
        msg_profile = f"👤 *Profil Askely*\n⭐ Points : {data[0]}\n📆 Membre depuis : {data[1][:10]}"
        resp.message(msg_profile)
        return str(resp)

    if "voir tous les avis" in msg_lower:
        avis = get_public_reviews()
        if avis:
            msg_avis = "\n\n".join([f"{a[0].capitalize()} ⭐{a[1]}/5 : {a[2]}" for a in avis])
        else:
            msg_avis = "Aucun avis pour l'instant."
        resp.message(f"🗣️ *Avis utilisateurs Askely*\n\n{msg_avis}")
        return str(resp)

    match_review = re.search(r"(vol|h[oô]tel|restaurant|fidélité) (\d)\/5 (.+)", msg_lower)
    if match_review:
        type_, note, commentaire = match_review.groups()
        note = int(note)
        points_map = {"vol": 50, "hôtel": 40, "hotel": 40, "restaurant": 30, "fidélité": 20}
        pts = points_map.get(type_, 10)
        save_review(phone_hash, type_, note, commentaire)
        points = add_points(phone_hash, pts)
        msg = f"Merci pour votre avis sur {type_} ! ⭐{note}/5\n🎁 +{pts} points\n🧾 Commentaire : {commentaire}\n🔗 Voir tous les avis"
        resp.message(msg)
        return str(resp)

    if "hôtel à" in msg_lower:
        ville = msg_lower.split("hôtel à")[-1].strip().title()
        resp.message(search_hotels(ville))
        return str(resp)

    if "restaurant à" in msg_lower:
        ville = msg_lower.split("restaurant à")[-1].strip().title()
        resp.message(search_restaurants(ville))
        return str(resp)

    if "vol de" in msg_lower and "vers" in msg_lower:
        parts = re.findall(r"vol de (.+) vers (.+)", msg_lower)
        if parts:
            origine, destination = parts[0]
            resp.message(search_flights(origine.title(), destination.title()))
            return str(resp)

    if "réclamation" in msg_lower or "bagage" in msg_lower:
        resp.message("📄 Réclamation en cours : bagage perdu ou endommagé.\nVeuillez fournir plus de détails.")
        return str(resp)

    if "plan à" in msg_lower:
        ville = msg_lower.split("plan à")[-1].strip().title()
        resp.message(generate_travel_plan(ville))
        return str(resp)

    if "bons plans au" in msg_lower:
        pays = msg_lower.split("bons plans au")[-1].strip().title()
        resp.message(get_travel_deals(pays))
        return str(resp)

    try:
        réponse = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Tu es Askely, un assistant de conciergerie intelligent."},
                {"role": "user", "content": msg_corrigé}
            ],
            max_tokens=300
        )
        result = réponse.choices[0].message["content"]
    except Exception:
        result = "❌ Une erreur est survenue avec GPT."

    resp.message(result)
    return str(resp)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
