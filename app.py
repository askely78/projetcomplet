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

# ----------------------
# Initialisation BDD
# ----------------------
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_phone TEXT,
            category TEXT,
            name TEXT,
            note INTEGER,
            avis TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# ----------------------
# Gestion utilisateur
# ----------------------
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

# ----------------------
# Fonctionnalités IA et services
# ----------------------
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
    hotels = [f"{city} Palace", f"Riad {city} Medina", f"Dar Atlas {city}", f"Luxury Stay {city}", f"Hotel Central {city}"]
    return "\n".join([f"\ud83c\udfe8 H\u00f4tels \u00e0 {city} :"] + [f"{i+1}. {h}" for i, h in enumerate(hotels)])

def search_restaurants(city, cuisine=None):
    if cuisine:
        return f"\ud83c\udf7d\ufe0f Restaurants {cuisine} \u00e0 {city} :\n1. Saveurs {cuisine}\n2. Chez {cuisine} House\n3. D\u00e9lices de {cuisine}"
    return f"\ud83c\udf7d\ufe0f Restaurants populaires \u00e0 {city} :\n1. La Table\n2. Resto Bahia\n3. Caf\u00e9 du Coin"

def search_flights(origin, destination):
    return f"\u2708\ufe0f Vols de {origin} \u00e0 {destination} :\n1. RAM - 08h00\n2. Air Arabia - 13h30\n3. EasyJet - 18h45"

def generate_baggage_claim():
    return "\ud83d\udcc4 R\u00e9clamation :\nMon bagage a \u00e9t\u00e9 perdu/endommag\u00e9. Merci de traiter cette demande."

def generate_travel_plan(city):
    return f"\ud83d\uddcc\ufe0f Plan de voyage \u00e0 {city} :\n- Jour 1 : visites culturelles\n- Jour 2 : activit\u00e9s locales\n- Jour 3 : gastronomie"

def get_travel_deals(country):
    return f"\ud83d\udca1 Bons plans au {country} :\n- R\u00e9ductions h\u00f4tels\n- March\u00e9s locaux\n- Transports \u00e0 prix r\u00e9duit\n- Tours guid\u00e9s"

def handle_evaluation(phone_number, msg):
    pattern = r"evaluation (compagnie|hotel|restaurant): (.*?), note: (\d), avis: (.+)"
    match = re.search(pattern, msg, re.IGNORECASE)
    if match:
        category, name, note, avis = match.groups()
        conn = sqlite3.connect("askely.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO evaluations (user_phone, category, name, note, avis) VALUES (?, ?, ?, ?, ?)",
                       (phone_number, category, name.strip(), int(note), avis.strip()))
        conn.commit()
        conn.close()
        points = add_points_to_user(phone_number, 10)
        return f"\u2705 Merci pour votre avis sur {name.strip()} ({category}) !\n\ud83d\udcc8 +10 points Askely. Total actuel : {points} ⭐️"
    return None

def handle_avis_consultation(msg):
    pattern = r"voir avis (compagnie|hotel|restaurant)"
    match = re.search(pattern, msg, re.IGNORECASE)
    if match:
        category = match.group(1)
        conn = sqlite3.connect("askely.db")
        cursor = conn.cursor()
        cursor.execute("SELECT name, note, avis FROM evaluations WHERE category = ? ORDER BY created_at DESC LIMIT 5", (category,))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return f"Aucun avis pour les {category}s."
        text = f"\ud83d\udcdc Avis r\u00e9cents sur les {category}s :\n"
        for r in rows:
            text += f"- {r[0]} ⭐{r[1]}/5 : {r[2]}\n"
        return text
    return None

# ----------------------
# Webhook WhatsApp
# ----------------------
@app.route("/webhook/whatsapp-webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    phone_number = request.values.get("From", "").replace("whatsapp:", "")
    country = request.values.get("WaId", "")[:2] if request.values.get("WaId") else "unknown"
    language = "auto"

    create_user_profile(phone_number, country, language)
    corrected_msg = corriger_message(incoming_msg)
    msg_lower = corrected_msg.lower()

    # PROFIL UTILISATEUR
    if "mon profil" in msg_lower or "mes points" in msg_lower:
        phone_hash = hash_phone_number(phone_number)
        conn = sqlite3.connect("askely.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, points, created_at FROM users WHERE phone_hash = ?", (phone_hash,))
        data = cursor.fetchone()
        conn.close()
        if data:
            user_id, points, created_at = data
            msg = f"\ud83d\udc64 *Votre Profil Askely*\n🆔 ID : {user_id}\n⭐ Points : {points}\n📅 Inscrit le : {created_at[:10]}"
        else:
            msg = "Profil introuvable."
        resp = MessagingResponse()
        resp.message(msg)
        return str(resp)

    # ÉVALUATION
    eval_msg = handle_evaluation(phone_number, msg_lower)
    if eval_msg:
        resp = MessagingResponse()
        resp.message(eval_msg)
        return str(resp)

    # AVIS CONSULTATION
    avis_msg = handle_avis_consultation(msg_lower)
    if avis_msg:
        resp = MessagingResponse()
        resp.message(avis_msg)
        return str(resp)

    # Services existants...
    # (à compléter si nécessaire)

    # IA par défaut
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Tu es Askely, un assistant de voyage intelligent."},
                {"role": "user", "content": corrected_msg}
            ],
            max_tokens=300
        )
        answer = response.choices[0].message["content"]
    except Exception:
        answer = "\u274c Erreur GPT."

    points = add_points_to_user(phone_number, 1)
    resp = MessagingResponse()
    resp.message(f"{answer}\n\ud83c\udf81 +1 point Askely. Total : {points} ⭐️")
    return str(resp)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
