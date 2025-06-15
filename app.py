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

# ------------------ BASE DE DONNÉES ------------------
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

# ------------------ FONCTIONS UTILITAIRES ------------------
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
    return cursor.fetchall()

def get_public_reviews(n=5):
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("SELECT type, rating, comment FROM reviews ORDER BY created_at DESC LIMIT ?", (n,))
    return cursor.fetchall()

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
    except:
        return msg

def parse_evaluation_message(msg):
    patterns = {
        "vol": r"évaluation\s+vol[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
        "hôtel": r"évaluation\s+h[oô]tel[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
        "restaurant": r"évaluation\s+restaurant[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
        "fidélité": r"évaluation\s+fidélité[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)"
    }
    for review_type, pattern in patterns.items():
        match = re.match(pattern, msg, re.IGNORECASE)
        if match:
            return review_type, int(match.group(2)), match.group(3)
    return None, None, None

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
        "⭐ *Évaluer un vol/hôtel/restaurant/fidélité*\n"
        "📋 *Voir tous les avis*\n"
        "👤 *Mon profil / Mes points*\n"
        "📌 Tapez *menu* à tout moment pour revoir ces options 😉"
    )

def get_welcome_message():
    return (
        "🎉 Bienvenue sur Askely !\n"
        "Vous voulez noter votre vol, votre séjour dans un hôtel ou votre expérience dans un restaurant ?\n"
        "Vous serez récompensé par :\n"
        "✈️ 10 points pour les vols\n"
        "🏨 7 points pour les hôtels\n"
        "🍽️ 5 points pour les restaurants\n\n"
        "Ou vous avez une demande qui concerne votre voyage ? Cela n’est pas récompensé.\n\n"
        "Commencez l’expérience dès maintenant et gagnez des points à chaque avis !"
    )

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

# ------------------ ROUTE PRINCIPALE ------------------
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
        conn = sqlite3.connect("askely.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET greeted = 1 WHERE phone_hash = ?", (phone_hash,))
        conn.commit()
        conn.close()
        return str(response)

    incoming_msg = corriger_message(incoming_msg)

    if incoming_msg.lower() in ["menu", "aide"]:
        msg.body(get_main_menu())
        return str(response)

    if "voir tous les avis" in incoming_msg.lower():
        reviews = get_public_reviews()
        avis = "\n".join([f"{r[0]} ⭐{r[1]} – {r[2]}" for r in reviews])
        msg.body(f"📋 Avis récents :\n{avis}")
        return str(response)

    if "mon profil" in incoming_msg.lower() or "mes points" in incoming_msg.lower():
        conn = sqlite3.connect("askely.db")
        cursor = conn.cursor()
        cursor.execute("SELECT points, created_at FROM users WHERE phone_hash = ?", (phone_hash,))
        row = cursor.fetchone()
        msg.body(f"👤 *Profil utilisateur Askely*\n📅 Inscrit depuis : {row[1][:10]}\n🏆 Points : {row[0]}")
        return str(response)

    review_type, rating, comment = parse_evaluation_message(incoming_msg)
    if review_type:
        points_map = {"vol": 10, "hôtel": 7, "restaurant": 5, "fidélité": 3}
        save_review(phone_hash, review_type, rating, comment)
        new_points = add_points(phone_hash, points_map.get(review_type, 0))
        msg.body(f"✅ Merci pour votre avis sur le {review_type} !\n⭐ Note : {rating}\n📝 Commentaire : {comment}\n🎉 Vous avez gagné {points_map[review_type]} points.\n🏆 Total : {new_points} points.")
        last_reviews = get_last_reviews(phone_hash)
        if last_reviews:
            msg.body("\n📋 Vos derniers avis :\n" + "\n".join([f"{r[0]} ⭐{r[1]} – {r[2]}" for r in last_reviews]))
            msg.body("🔗 Voir tous les avis")
        return str(response)

    if m := re.search(r"h[oô]tel[s]? à ([\w\s\-]+)", incoming_msg, re.IGNORECASE):
        msg.body(search_hotels(m.group(1).strip()))
        return str(response)

    if m := re.search(r"restaurant[s]? à ([\w\s\-]+)", incoming_msg, re.IGNORECASE):
        msg.body(search_restaurants(m.group(1).strip()))
        return str(response)

    if m := re.search(r"vol de ([\w\s\-]+) vers ([\w\s\-]+)", incoming_msg, re.IGNORECASE):
        msg.body(search_flights(m.group(1).strip(), m.group(2).strip()))
        return str(response)

    if m := re.search(r"plan à ([\w\s\-]+)", incoming_msg, re.IGNORECASE):
        msg.body(generate_travel_plan(m.group(1).strip()))
        return str(response)

    if m := re.search(r"bons plans au ([\w\s\-]+)", incoming_msg, re.IGNORECASE):
        msg.body(get_travel_deals(m.group(1).strip()))
        return str(response)

    if "bagage" in incoming_msg.lower():
        msg.body("🧳 Pour une réclamation de bagage, veuillez contacter la compagnie avec votre numéro de vol. Je peux vous aider à rédiger une réclamation.")
        return str(response)

    try:
        gpt = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Tu es Askely, un assistant de voyage multilingue."},
                {"role": "user", "content": incoming_msg}
            ],
            max_tokens=200
        )
        msg.body(gpt.choices[0].message["content"])
    except:
        msg.body("❌ Erreur avec l’intelligence artificielle. Veuillez réessayer plus tard.")

    return str(response)

# ------------------ LANCEMENT ------------------
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
