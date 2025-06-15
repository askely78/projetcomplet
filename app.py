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
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            greeted INTEGER DEFAULT 0
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
    cursor.execute("INSERT INTO users (id, phone_hash, country, language, points, created_at, greeted) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (user_id, phone_hash, country, language, 0, datetime.now(timezone.utc).isoformat(), 0))
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
        "🎉 *Bienvenue sur Askely !* 🎉\n\n"
        "Vous voulez noter votre vol, votre séjour dans un hôtel ou votre expérience dans un restaurant ?\n"
        "Vous serez récompensé par :\n"
        "✈️ 10 points pour les vols\n"
        "🏨 7 points pour les hôtels\n"
        "🍽️ 5 points pour les restaurants\n"
        "🎁 8 points pour les programmes de fidélité\n\n"
        "Ou vous avez une demande qui concerne votre voyage ?\n"
        "Cela n’est pas récompensé.\n\n"
        "Tapez *menu* pour commencer ✨"
    )

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

def parse_evaluation_message(msg):
    patterns = {
        "vol": r"évaluation\s+vol[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
        "hôtel": r"évaluation\s+h[oô]tel[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
        "restaurant": r"évaluation\s+restaurant[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
        "fidélité": r"évaluation\s+fidélité[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
    }
    for review_type, pattern in patterns.items():
        match = re.search(pattern, msg, re.IGNORECASE)
        if match:
            return review_type, int(match.group(2)), match.group(3).strip()
    return None, None, None

def guided_review_step(user_id, step, msg):
    steps = [
        "Quel type d’évaluation souhaitez-vous faire ? (vol, hôtel, restaurant, fidélité)",
        "Quel est le nom ou la référence ?",
        "Quelle est votre note sur 5 ?",
        "Votre avis en quelques mots ?"
    ]
    if step < len(steps):
        return steps[step]
    return None

def search_hotels(city):
    hotels = [f"{city} Palace", f"Riad {city}", f"Dar Atlas {city}", f"Luxury Stay {city}", f"Hotel Central {city}"]
    return "\n".join([f"🏨 Hôtels à {city} :"] + [f"{i+1}. {h}" for i, h in enumerate(hotels)])

def search_restaurants(city):
    restos = [f"{city} Gourmet", f"Bistro {city}", f"Chez {city}", f"La Table {city}", f"Café Medina"]
    return "\n".join([f"🍽️ Restaurants à {city} :"] + [f"{i+1}. {r}" for i, r in enumerate(restos)])

def search_flights(origin, dest):
    vols = [
        f"Air {origin}-{dest} à 8h30",
        f"{origin} Express vers {dest} à 13h45",
        f"Royal {origin}-{dest} à 21h00"
    ]
    return "\n".join([f"✈️ Vols de {origin} vers {dest} :"] + [f"{i+1}. {v}" for i, v in enumerate(vols)])

def generate_travel_plan(city):
    return (
        f"🗺️ Circuit touristique à {city} :\n"
        "1. Matin : Visite historique\n"
        "2. Midi : Déjeuner local\n"
        "3. Après-midi : Souks / musées\n"
        "4. Soir : Dîner et animations"
    )

def get_travel_deals(country):
    return (
        f"💡 Bons plans au {country} :\n"
        "- Réductions duty free\n"
        "- Excursions locales à moitié prix\n"
        "- Restaurants partenaires avec cadeaux\n"
        "- Entrées gratuites dans certains musées"
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

    # Afficher le message de bienvenue à la première interaction
    if not greeted:
        msg.body(get_welcome_message())
        mark_greeted(phone_hash)
        return str(response)

    # Corriger le message de l'utilisateur
    incoming_msg = corriger_message(incoming_msg)

    # Commande menu
    if incoming_msg.lower() in ["menu", "aide"]:
        msg.body(get_main_menu())
        return str(response)

    # Voir tous les avis
    if "voir tous les avis" in incoming_msg.lower():
        reviews = get_public_reviews()
        avis = "\n".join([f"{r[0]} ⭐{r[1]} – {r[2]}" for r in reviews])
        msg.body(f"📋 Avis récents :\n{avis}")
        return str(response)

    # Voir mon profil
    if "mon profil" in incoming_msg.lower() or "mes points" in incoming_msg.lower():
        conn = sqlite3.connect("askely.db")
        cursor = conn.cursor()
        cursor.execute("SELECT points, created_at FROM users WHERE phone_hash = ?", (phone_hash,))
        row = cursor.fetchone()
        conn.close()
        points = row[0]
        inscrit = row[1][:10]
        msg.body(f"👤 *Profil utilisateur Askely*\n📅 Inscrit depuis : {inscrit}\n🏆 Points : {points}")
        return str(response)

    # Évaluations
    review_type, rating, comment = parse_evaluation_message(incoming_msg)
    if review_type:
        points_map = {"vol": 10, "hôtel": 7, "restaurant": 5, "fidélité": 8}
        save_review(phone_hash, review_type, rating, comment)
        earned = points_map.get(review_type, 0)
        total = add_points(phone_hash, earned)
        msg.body(f"✅ Merci pour votre avis sur le {review_type} !\n⭐ Note : {rating}\n📝 Commentaire : {comment}\n\n🎉 Vous avez gagné {earned} points.\n🏆 Total : {total} points.")
        reviews = get_last_reviews(phone_hash)
        if reviews:
            msg.body("\n📋 Vos derniers avis :\n" + "\n".join([f"{r[0]} ⭐{r[1]} – {r[2]}" for r in reviews]))
            msg.body("🔗 Voir tous les avis")
        return str(response)

    # Recherche hôtel
    hotel_match = re.search(r"h[oô]tel[s]? à ([\w\s\-]+)", incoming_msg, re.IGNORECASE)
    if hotel_match:
        city = hotel_match.group(1).strip()
        msg.body(search_hotels(city))
        return str(response)

    # Recherche restaurant
    resto_match = re.search(r"restaurant[s]? à ([\w\s\-]+)", incoming_msg, re.IGNORECASE)
    if resto_match:
        city = resto_match.group(1).strip()
        msg.body(search_restaurants(city))
        return str(response)

    # Recherche vol
    vol_match = re.search(r"vol de ([\w\s\-]+) vers ([\w\s\-]+)", incoming_msg, re.IGNORECASE)
    if vol_match:
        origine = vol_match.group(1).strip()
        destination = vol_match.group(2).strip()
        msg.body(search_flights(origine, destination))
        return str(response)

    # Plan touristique
    plan_match = re.search(r"plan à ([\w\s\-]+)", incoming_msg, re.IGNORECASE)
    if plan_match:
        city = plan_match.group(1).strip()
        msg.body(generate_travel_plan(city))
        return str(response)

    # Bons plans
    deals_match = re.search(r"bons plans au ([\w\s\-]+)", incoming_msg, re.IGNORECASE)
    if deals_match:
        country = deals_match.group(1).strip()
        msg.body(get_travel_deals(country))
        return str(response)

    # Réclamation bagage
    if "bagage" in incoming_msg.lower():
        msg.body("🧳 Pour une réclamation de bagage, veuillez contacter la compagnie avec votre numéro de vol. Si vous avez besoin d’aide pour rédiger un message officiel, je peux vous aider.")
        return str(response)

    # Question libre traitée par GPT-4o
    try:
        reply = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Tu es Askely, un assistant de voyage intelligent et multilingue."},
                {"role": "user", "content": incoming_msg}
            ],
            max_tokens=250
        )
        msg.body(reply.choices[0].message["content"])
    except:
        msg.body("❌ Erreur avec l’intelligence artificielle. Veuillez réessayer plus tard.")

    return str(response)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
