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
            user_id TEXT,
            type TEXT,
            nom TEXT,
            note INTEGER,
            avis TEXT,
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

def save_evaluation(user_id, type_eval, nom, note, avis):
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO evaluations (user_id, type, nom, note, avis, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, type_eval, nom, note, avis, datetime.now(timezone.utc))
    )
    conn.commit()
    conn.close()

def get_evaluations(type_eval, limit=5):
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT nom, note, avis FROM evaluations WHERE type = ? ORDER BY created_at DESC LIMIT ?",
        (type_eval, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows

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

def parse_evaluation_message(msg):
    patterns = {
        "compagnie": r"évaluation\s+compagnie[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
        "hotel": r"évaluation\s+hotel[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
        "restaurant": r"évaluation\s+restaurant[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
    }
    for type_eval, pattern in patterns.items():
        match = re.search(pattern, msg, re.IGNORECASE)
        if match:
            nom = match.group(1).strip()
            note = int(match.group(2).strip())
            avis = match.group(3).strip()
            return type_eval, nom, note, avis
    return None

def guide_rapide_message():
    return (
        "📚 *Guide rapide d’utilisation Askely* 📚\n\n"
        "1️⃣ Consulte ton profil et tes points :\n   tape *mon profil* ou *mes points*\n\n"
        "2️⃣ Cherche un hôtel ou restaurant :\n   ex: *hôtel à Marrakech* ou *restaurant italien à Casablanca*\n\n"
        "3️⃣ Trouve un vol :\n   ex: *vol de Paris vers Marrakech*\n\n"
        "4️⃣ Demande un plan de voyage :\n   ex: *plan de voyage à Agadir*\n\n"
        "5️⃣ Découvre les bons plans :\n   ex: *bons plans au Maroc*\n\n"
        "6️⃣ Fais une réclamation bagage :\n   tape *réclamation bagage*\n\n"
        "7️⃣ Donne ton avis et gagne des points :\n"
        "   ex: évaluation compagnie: Air France, note: 4, avis: Bon service\n\n"
        "8️⃣ Consulte les avis des autres :\n   tape *voir avis compagnie* ou *voir avis hôtel* ou *voir avis restaurant*\n\n"
        "9️⃣ Pose toutes tes questions ! Askely te répond.\n\n"
        "⭐ Gagne des points à chaque interaction utile !\n"
        "Tape *mon profil* pour voir tes points."
    )

@app.route("/webhook/whatsapp-webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    phone_number = request.values.get("From", "").replace("whatsapp:", "")
    country = request.values.get("WaId", "")[:2] if request.values.get("WaId") else "unknown"
    language = "auto"

    create_user_profile(phone_number, country, language)

    corrected_msg = corriger_message(incoming_msg)
    msg_lower = corrected_msg.lower()

    resp = MessagingResponse()

    # Envoi guide rapide si demandé
    if "guide" in msg_lower or "aide" in msg_lower:
        resp.message(guide_rapide_message())
        return str(resp)

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
            msg = f"👤 *Votre Profil Askely*\n🆔 ID : {user_id}\nPoints : {points}\nInscrit le : {created_at[:10]}"
        else:
            msg = "Profil introuvable. Avez-vous déjà utilisé Askely ?"

        resp.message(msg)
        return str(resp)

    # Consultation des avis
    if "voir avis" in msg_lower:
        if "compagnie" in msg_lower:
            type_eval = "compagnie"
        elif "hotel" in msg_lower:
            type_eval = "hotel"
        elif "restaurant" in msg_lower:
            type_eval = "restaurant"
        else:
            resp.message("❗ Veuillez préciser : voir avis compagnie, hôtel ou restaurant.")
            return str(resp)

        avis_list = get_evaluations(type_eval)
        if not avis_list:
            resp.message(f"Aucun avis pour les {type_eval}s.")
            return str(resp)

        msg = f"📝 Derniers avis sur les {type_eval}s :\n"
        for nom, note, avis in avis_list:
            msg += f"- {nom} ⭐{note}/5 : {avis}\n"
        resp.message(msg)
        return str(resp)

    # Traitement évaluation (note + avis)
    eval_parsed = parse_evaluation_message(corrected_msg)
    if eval_parsed:
        type_eval, nom, note, avis = eval_parsed
        phone_hash = hash_phone_number(phone_number)
        conn = sqlite3.connect("askely.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE phone_hash = ?", (phone_hash,))
        user_row = cursor.fetchone()
        conn.close()
        if user_row:
            user_id = user_row[0]
            save_evaluation(user_id, type_eval, nom, note, avis)
            points = add_points_to_user(phone_number, 10)  # +10 points pour une évaluation
            resp.message(f"✅ Merci pour votre avis sur {nom} ({type_eval}) !\n🟢 Vous gagnez +10 points Askely ! Total : {points}\n📌 Tapez *mon profil* pour consulter vos points.")
            return str(resp)

    # Hôtels
    match_hotel = re.search(r"h[oô]tel(?: à| a)? ([\w\s\-]+)", msg_lower)
    if match_hotel:
        city = match_hotel.group(1).strip().title()
        hotels = [f"Hôtel {i+1} à {city}" for i in range(5)]
        message = "🏨 Suggestions d'hôtels :\n" + "\n".join(hotels)
        points = add_points_to_user(phone_number, 1)
        msg = f"{message}\n\n🎁 Vous gagnez 1 point Askely ! Total : {points}\n📌 Tapez *mon profil* pour consulter vos points."
        resp.message(msg)
        return str(resp)

    # Restaurants
    match_restaurant = re.search(r"restaurant(?: [\w]+)?(?: à| a)? ([\w\s\-]+)", msg_lower)
    if match_restaurant:
        city = match_restaurant.group(1).strip().title()
        restos = [f"Restaurant {i+1} à {city}" for i in range(5)]
        message = "🍽️ Suggestions de restaurants :\n" + "\n".join(restos)
        points = add_points_to_user(phone_number, 1)
        msg = f"{message}\n\n🎁 Vous gagnez 1 point Askely ! Total : {points}\n📌 Tapez *mon profil* pour consulter vos points."
        resp.message(msg)
        return str(resp)

    # Vols
    match_flight = re.search(r"vol(?: de)? ([\w\s]+) vers ([\w\s]+)", msg_lower)
    if match_flight:
        origin = match_flight.group(1).strip().title()
        destination = match_flight.group(2).strip().title()
        flights = search_flights(origin, destination)
        points = add_points_to_user(phone_number, 1)
        msg = f"{flights}\n\n🎁 Vous gagnez 1 point Askely ! Total : {points}\n📌 Tapez *mon profil* pour consulter vos points."
        resp.message(msg)
        return str(resp)

    # Réclamations bagage
    if "bagage" in msg_lower or "réclamation" in msg_lower:
        result = generate_baggage_claim()
        points = add_points_to_user(phone_number, 2)
        msg = f"{result}\n\n🎁 Vous gagnez 2 points Askely ! Total : {points}\n📌 Tapez *mon profil* pour consulter vos points."
        resp.message(msg)
        return str(resp)

    # Plan de voyage
    match_plan = re.search(r"(plan|itinéraire)(?: à| pour)? ([\w\s\-]+)", msg_lower)
    if match_plan:
        city = match_plan.group(2).strip().title()
        plan = generate_travel_plan(city)
        points = add_points_to_user(phone_number, 2)
        msg = f"{plan}\n\n🎁 Vous gagnez 2 points Askely ! Total : {points}\n📌 Tapez *mon profil* pour consulter vos points."
        resp.message(msg)
        return str(resp)

    # Bons plans
    match_deal = re.search(r"bons? plans? (?:au|en|dans le)? ([\w\s\-]+)", msg_lower)
    if match_deal:
        country = match_deal.group(1).strip().title()
        deals = get_travel_deals(country)
        points = add_points_to_user(phone_number, 1)
        msg = f"{deals}\n\n🎁 Vous gagnez 1 point Askely ! Total : {points}\n📌 Tapez *mon profil* pour consulter vos points."
        resp.message(msg)
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
    msg = f"{answer}\n\n🎁 Vous gagnez 1 point Askely ! Total : {points}\n📌 Tapez *mon profil* pour consulter vos points."
    resp.message(msg)
    return str(resp)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
