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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_phone TEXT,
            type TEXT,
            nom TEXT,
            note INTEGER,
            avis TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_phone TEXT,
            type TEXT,
            valeur TEXT,
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

def add_points_to_user(phone_number, points=10):
    phone_hash = hash_phone_number(phone_number)
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET points = points + ? WHERE phone_hash = ?", (points, phone_hash))
    cursor.execute("SELECT points FROM users WHERE phone_hash = ?", (phone_hash,))
    new_points = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return new_points
def log_interaction(phone, type_inter, valeur):
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO interactions (user_phone, type, valeur) VALUES (?, ?, ?)", (phone, type_inter, valeur))
    conn.commit()
    conn.close()

def has_interaction(phone, type_inter, nom):
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM interactions WHERE user_phone = ? AND type = ? AND valeur LIKE ?",
                   (phone, type_inter, f"%{nom}%"))
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0

@app.route("/webhook/whatsapp-webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    phone_number = request.values.get("From", "").replace("whatsapp:", "")
    create_user_profile(phone_number)
    msg_lower = incoming_msg.lower()
    # --- RECHERCHE VOL ---
    match_flight = re.search(r"vol(?: de)? ([\\w\\s]+) vers ([\\w\\s]+)", msg_lower)
    if match_flight:
        origin = match_flight.group(1).strip().title()
        destination = match_flight.group(2).strip().title()
        log_interaction(phone_number, "vol", f"{origin} → {destination}")
        result = f"✈️ Vols de {origin} à {destination} :\n1. RAM - 08h00\n2. Air Arabia - 13h30\n3. EasyJet - 18h45"
        resp = MessagingResponse()
        resp.message(result)
        return str(resp)

    # --- RECHERCHE HÔTEL ---
    match_hotel = re.search(r"h[oô]tel(?: à| a)? ([\\w\\s\\-]+)", msg_lower)
    if match_hotel:
        city = match_hotel.group(1).strip().title()
        log_interaction(phone_number, "hotel", city)
        result = f"🏨 Hôtels recommandés à {city} :\n1. Atlas Palace\n2. Riad Medina\n3. Hôtel des Arts"
        resp = MessagingResponse()
        resp.message(result)
        return str(resp)

    # --- RECHERCHE RESTAURANT ---
    match_restaurant = re.search(r"restaurant(?: [\\w]+)?(?: à| a)? ([\\w\\s\\-]+)", msg_lower)
    if match_restaurant:
        city = match_restaurant.group(1).strip().title()
        log_interaction(phone_number, "restaurant", city)
        result = f"🍽️ Restaurants à {city} :\n1. Le Gourmet\n2. Saveurs Atlas\n3. Beldi Resto"
        resp = MessagingResponse()
        resp.message(result)
        return str(resp)

    # --- CIRCUITS TOURISTIQUES ---
    match_circuit = re.search(r"(?:circuit|visite|tour) (?:à|de|dans)? ([\\w\\s\\-]+)", msg_lower)
    if match_circuit:
        city = match_circuit.group(1).strip().title()
        log_interaction(phone_number, "circuit", city)
        result = f"🗺️ Circuit touristique à {city} :\n- Jour 1 : Centre historique\n- Jour 2 : Artisanat\n- Jour 3 : Gastronomie"
        resp = MessagingResponse()
        resp.message(result)
        return str(resp)

    # --- BONS PLANS ---
    match_deal = re.search(r"bons? plans? (?:au|en|dans le)? ([\\w\\s\\-]+)", msg_lower)
    if match_deal:
        country = match_deal.group(1).strip().title()
        log_interaction(phone_number, "bons plans", country)
        result = f"💡 Bons plans au {country} :\n- Réduction hôtels\n- Transports pas chers\n- Activités locales"
        resp = MessagingResponse()
        resp.message(result)
        return str(resp)

    # --- RÉCLAMATION BAGAGE ---
    if "bagage" in msg_lower and ("perdu" in msg_lower or "endommagé" in msg_lower or "réclamation" in msg_lower):
        log_interaction(phone_number, "bagage", "réclamation")
        result = "📄 Réclamation enregistrée : bagage perdu ou endommagé. Merci de fournir les détails complémentaires."
        resp = MessagingResponse()
        resp.message(result)
        return str(resp)
    # Évaluation vol: AT203, Casablanca → Paris, Royal Air Maroc, ⭐⭐⭐⭐, avis: Très ponctuel.
    match_vol = re.search(r"évaluation vol[:\\-]?\\s*(\\w+),\\s*(.*?→.*?),\\s*(.*?),\\s*⭐{1,5},\\s*avis[:\\-]?\\s*(.+)", msg_lower)
    if match_vol:
        numero_vol = match_vol.group(1).strip().upper()
        trajet = match_vol.group(2).strip().title()
        compagnie = match_vol.group(3).strip().title()
        avis = match_vol.group(4).strip()
        note = msg_lower.count("⭐")
        if not has_interaction(phone_number, "vol", trajet):
            resp = MessagingResponse()
            resp.message("❌ Pour évaluer ce vol, vous devez d’abord l’avoir recherché avec Askely.")
            return str(resp)
        conn = sqlite3.connect("askely.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO evaluations (user_phone, type, nom, note, avis) VALUES (?, ?, ?, ?, ?)",
                       (phone_number, "vol", f"{numero_vol} - {compagnie}", note, avis))
        conn.commit()
        conn.close()
        points = add_points_to_user(phone_number, 10)
        resp = MessagingResponse()
        resp.message(
            f"✅ Merci pour votre avis sur le vol {numero_vol} avec {compagnie} ! ⭐{note}/5\\n"
            f"🎁 +10 points Askely. Total : {points} ⭐"
        )
        return str(resp)

    # Évaluations hôtel, restaurant, fidélité
    eval_patterns = {
        "hotel": r"évaluation hôtel[:\\-]?\\s*(.*?),\\s*⭐{1,5},\\s*avis[:\\-]?\\s*(.+)",
        "restaurant": r"évaluation restaurant[:\\-]?\\s*(.*?),\\s*⭐{1,5},\\s*avis[:\\-]?\\s*(.+)",
        "fidelite": r"évaluation fidélité[:\\-]?\\s*(.*?),\\s*⭐{1,5},\\s*avis[:\\-]?\\s*(.+)"
    }

    for type_eval, pattern in eval_patterns.items():
        match = re.search(pattern, msg_lower)
        if match:
            nom = match.group(1).strip().title()
            avis = match.group(2).strip()
            note = msg_lower.count("⭐")
            if not has_interaction(phone_number, type_eval, nom):
                resp = MessagingResponse()
                resp.message(f"❌ Pour évaluer {nom}, vous devez d'abord l’avoir consulté via Askely.")
                return str(resp)
            conn = sqlite3.connect("askely.db")
            cursor = conn.cursor()
            cursor.execute("INSERT INTO evaluations (user_phone, type, nom, note, avis) VALUES (?, ?, ?, ?, ?)",
                           (phone_number, type_eval, nom, note, avis))
            conn.commit()
            conn.close()
            points = add_points_to_user(phone_number, 10)
            resp = MessagingResponse()
            resp.message(
                f"✅ Merci pour votre avis sur {nom} ({type_eval}) ! ⭐{note}/5\\n"
                f"🎁 +10 points Askely. Total : {points} ⭐"
            )
            return str(resp)

    # Message d’accueil
    accueil = (
        "👋 Bienvenue sur *Askely*, votre assistant de voyage 🌍\\n\\n"
        "📌 Vous pouvez :\\n"
        "- chercher un hôtel\\n- trouver un restaurant\\n- comparer des vols\\n- évaluer vos expériences\\n\\n"
        "*Exemples d'évaluation* :\\n"
        "Évaluation vol: AT203, Casablanca → Paris, Royal Air Maroc, ⭐⭐⭐⭐, avis: Très ponctuel.\\n"
        "Évaluation hôtel: Hôtel Atlas, ⭐⭐⭐⭐, avis: Accueil chaleureux.\\n"
        "Évaluation restaurant: Dar Yacout, ⭐⭐⭐⭐, avis: Excellent tajine.\\n"
        "Évaluation fidélité: Flying Blue, ⭐⭐⭐⭐, avis: Facile à utiliser.\\n"
        "✅ Vous gagnez +10 points à chaque avis validé."
    )
    resp = MessagingResponse()
    resp.message(accueil)
    return str(resp)
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
