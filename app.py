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
            greeted INTEGER DEFAULT 0,
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
    user = cursor.fetchone()
    if user:
        conn.close()
        return user[0], user[6]
    user_id = f"askely_{uuid.uuid4().hex[:8]}"
    cursor.execute("INSERT INTO users (id, phone_hash, country, language, points, greeted, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (user_id, phone_hash, country, language, 0, 0, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()
    return user_id, 0

def mark_greeted(phone_hash):
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET greeted = 1 WHERE phone_hash = ?", (phone_hash,))
    conn.commit()
    conn.close()

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

def get_main_menu():
    return (
        "🤖 *Bienvenue sur Askely* – Votre concierge intelligent 🌍\n\n"
        "Voici ce que vous pouvez faire 👇\n\n"
        "🏨 *Hôtel à [ville]* – Rechercher des hôtels\n"
        "🍽️ *Restaurant à [ville]* – Trouver des restaurants\n"
        "✈️ *Vol de [ville A] vers [ville B]* – Voir les options de vols\n"
        "🧳 *Réclamation bagage* – Aide pour bagage perdu ou endommagé\n"
        "🗺️ *Plan à [ville]* – Circuit touristique jour par jour\n"
        "💡 *Bons plans au [pays]* – Les meilleures offres locales\n"
        "⭐ *Évaluer un vol/hôtel/restaurant/fidélité* – Laisser un avis avec une note\n"
        "📋 *Voir tous les avis* – Afficher les avis des autres utilisateurs\n"
        "👤 *Mon profil* – Voir vos points et date d'inscription\n\n"
        "📌 Tapez *menu* à tout moment pour revoir ces options 😉"
    )

def get_welcome_message():
    return (
        "Bonjour !\n\n"
        "🎉 Bienvenue sur Askely, votre assistant personnel de voyage !\n\n"
        "Vous pouvez gagner des points en évaluant vos expériences :\n"
        "✈️ 10 points pour les vols\n"
        "🏨 7 points pour les hôtels\n"
        "🍽️ 5 points pour les restaurants\n"
        "💳 8 points pour les programmes de fidélité\n\n"
        "📋 Pour évaluer, suivez ce format :\n"
        "- évaluation vol: Royal Air Maroc, note: 5, avis: Très bon service\n"
        "- évaluation hôtel: Riad Atlas, note: 4, avis: Accueil chaleureux\n"
        "- évaluation restaurant: Dar Yacout, note: 5, avis: Excellent repas\n"
        "- évaluation fidélité: Safar Flyer, note: 4, avis: Bon programme\n\n"
        "Tapez *menu* pour commencer !"
    )
def parse_evaluation_message(msg):
    patterns = {
        "vol": r"évaluation\s+vol[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
        "hôtel": r"évaluation\s+h[oô]tel[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
        "restaurant": r"évaluation\s+restaurant[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
        "fidélité": r"évaluation\s+fidélité[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)"
    }
    for review_type, pattern in patterns.items():
        match = re.search(pattern, msg, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            note = int(match.group(2).strip())
            avis = match.group(3).strip()
            return review_type, note, f"{name} – {avis}"
    return None, None, None

def search_hotels(city):
    hotels = [f"{city} Palace", f"Riad {city}", f"Dar Atlas {city}", f"Luxury Stay {city}", f"Hotel Central {city}"]
    return "\n".join([f"🏨 Hôtels à {city} :"] + [f"{i+1}. {h}" for i, h in enumerate(hotels)])

def search_restaurants(city):
    restos = [f"{city} Gourmet", f"Bistro {city}", f"Chez {city}", f"La Table {city}", f"Café Medina"]
    return "\n".join([f"🍽️ Restaurants à {city} :"] + [f"{i+1}. {r}" for i, r in enumerate(restos)])

def search_flights(origin, dest):
    vols = [
        f"RAM {origin}-{dest} : 8h45, 1200 MAD",
        f"Air France {origin}-{dest} : 12h10, 230€",
        f"Transavia {origin}-{dest} : 15h20, 89€",
        f"EasyJet {origin}-{dest} : 17h45, 99€",
        f"Royal Air Maroc {origin}-{dest} : 20h00, 1350 MAD"
    ]
    return "\n".join([f"✈️ Vols entre {origin} et {dest} :"] + vols)

def generate_travel_plan(city):
    plan = [
        f"🗓️ Jour 1 : Découverte de la médina de {city}",
        f"🏛️ Jour 2 : Visite des musées et monuments",
        f"🌅 Jour 3 : Excursion dans les environs",
        f"🛍️ Jour 4 : Souks et shopping",
        f"🍽️ Jour 5 : Gastronomie locale"
    ]
    return "\n".join([f"📍 Circuit touristique à {city} :"] + plan)

def get_travel_deals(country):
    deals = [
        f"🏨 -30% sur hôtels au {country}",
        f"🍽️ Dîner offert pour 2 dans les restaurants partenaires",
        f"🚌 Transfert gratuit depuis l'aéroport",
        f"🎁 Cadeau de bienvenue pour les nouveaux voyageurs"
    ]
    return "\n".join([f"💡 Bons plans au {country} :"] + deals)

def dialogue_guidé_evaluation():
    return (
        "📋 *Évaluation guidée Askely*\n"
        "Veuillez envoyer votre évaluation sous l'un de ces formats :\n\n"
        "1. Vol ✈️ :\n"
        "   évaluation vol: Air France, note: 5, avis: Très bon vol\n\n"
        "2. Hôtel 🏨 :\n"
        "   évaluation hôtel: Riad Yasmine, note: 4, avis: Bon séjour\n\n"
        "3. Restaurant 🍽️ :\n"
        "   évaluation restaurant: Chez Fatima, note: 5, avis: Excellent couscous\n\n"
        "4. Fidélité 💳 :\n"
        "   évaluation fidélité: Flying Blue, note: 3, avis: Peu d’avantages\n\n"
        "👉 Vous gagnerez des points pour chaque évaluation envoyée !"
    )
@app.route("/webhook/whatsapp-webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    from_number = request.values.get("From", "")
    country = request.values.get("WaId", "")[:2]
    phone_hash = hash_phone_number(from_number)
    user_id, greeted = create_user_profile(from_number, country)

    response = MessagingResponse()
    msg = response.message()

    if not greeted:
        msg.body(get_welcome_message())
        mark_greeted(phone_hash)
        return str(response)

    # Correction orthographique
    incoming_msg = corriger_message(incoming_msg)

    # Menu principal
    if incoming_msg.lower() in ["menu", "aide"]:
        msg.body(get_main_menu())
        return str(response)

    # Dialogue guidé pour évaluation
    if "évaluation guidée" in incoming_msg.lower():
        msg.body(dialogue_guidé_evaluation())
        return str(response)

    # Voir tous les avis
    if "voir tous les avis" in incoming_msg.lower():
        reviews = get_public_reviews()
        avis = "\n".join([f"{r[0]} ⭐{r[1]} – {r[2]}" for r in reviews])
        msg.body(f"📋 Avis récents :\n{avis}")
        return str(response)

    # Profil utilisateur
    if "mon profil" in incoming_msg.lower() or "mes points" in incoming_msg.lower():
        conn = sqlite3.connect("askely.db")
        cursor = conn.cursor()
        cursor.execute("SELECT points, created_at FROM users WHERE phone_hash = ?", (phone_hash,))
        row = cursor.fetchone()
        conn.close()
        points = row[0]
        inscrit = row[1][:10]
        msg.body(f"👤 *Profil Askely*\n📅 Inscrit le : {inscrit}\n🏆 Points : {points}")
        return str(response)

    # Évaluations
    review_type, rating, comment = parse_evaluation_message(incoming_msg)
    if review_type:
        points_map = {"vol": 10, "hôtel": 7, "restaurant": 5, "fidélité": 8}
        save_review(phone_hash, review_type, rating, comment)
        new_points = add_points(phone_hash, points_map.get(review_type, 0))
        msg.body(
            f"✅ Merci pour votre avis sur le {review_type} !\n"
            f"⭐ Note : {rating}\n📝 Commentaire : {comment}\n\n"
            f"🎉 Vous avez gagné {points_map[review_type]} points.\n🏆 Total : {new_points} points."
        )
        reviews = get_last_reviews(phone_hash)
        if reviews:
            msg.body("📋 Vos derniers avis :\n" + "\n".join([f"{r[0]} ⭐{r[1]} – {r[2]}" for r in reviews]))
            msg.body("🔗 Voir tous les avis")
        return str(response)

    # Hôtels
    hotel_match = re.search(r"h[oô]tel[s]? à ([\w\s\-]+)", incoming_msg, re.IGNORECASE)
    if hotel_match:
        city = hotel_match.group(1).strip()
        msg.body(search_hotels(city))
        return str(response)

    # Restaurants
    resto_match = re.search(r"restaurant[s]? à ([\w\s\-]+)", incoming_msg, re.IGNORECASE)
    if resto_match:
        city = resto_match.group(1).strip()
        msg.body(search_restaurants(city))
        return str(response)

    # Vols
    flight_match = re.search(r"vol de ([\w\s\-]+) vers ([\w\s\-]+)", incoming_msg, re.IGNORECASE)
    if flight_match:
        origin = flight_match.group(1).strip()
        dest = flight_match.group(2).strip()
        msg.body(search_flights(origin, dest))
        return str(response)

    # Plan de voyage
    plan_match = re.search(r"plan à ([\w\s\-]+)", incoming_msg, re.IGNORECASE)
    if plan_match:
        city = plan_match.group(1).strip()
        msg.body(generate_travel_plan(city))
        return str(response)

    # Bons plans
    bonplan_match = re.search(r"bons plans au ([\w\s\-]+)", incoming_msg, re.IGNORECASE)
    if bonplan_match:
        country = bonplan_match.group(1).strip()
        msg.body(get_travel_deals(country))
        return str(response)

    # Bagages
    if "bagage" in incoming_msg.lower() or "bagages" in incoming_msg.lower():
        msg.body("🧳 Pour une réclamation de bagage, contactez la compagnie avec vos références. Besoin d’aide pour rédiger une réclamation ? Je peux vous aider !")
        return str(response)

    # Question libre via GPT
    try:
        reply = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Tu es Askely, un assistant de voyage intelligent et multilingue."},
                {"role": "user", "content": incoming_msg}
            ],
            max_tokens=200
        )
        msg.body(reply.choices[0].message["content"])
    except Exception:
        msg.body("❌ Erreur avec l’intelligence artificielle. Réessayez plus tard.")

    return str(response)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
