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
        return user[0], user[6]  # user_id, greeted
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
        return user[0], user[6]  # user_id, greeted
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
@app.route("/webhook/whatsapp-webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    from_number = request.values.get("From", "")
    country = request.values.get("WaId", "")[:2]  # tentative détection pays
    phone_hash = hash_phone_number(from_number)

    user_id = create_user_profile(from_number, country)
    response = MessagingResponse()
    msg = response.message()

    # Afficher message d’accueil si première fois
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM reviews WHERE phone_hash = ?", (phone_hash,))
    review_count = cursor.fetchone()[0]
    conn.close()

    if review_count == 0 and incoming_msg.lower() not in ["menu", "mon profil", "mes points"]:
        msg.body(get_welcome_message())
        return str(response)

    # Corriger message
    incoming_msg = corriger_message(incoming_msg)

    # Si l'utilisateur demande le menu
    if incoming_msg.lower() in ["menu", "aide"]:
        msg.body(get_main_menu())
        return str(response)

    # Voir tous les avis
    if "voir tous les avis" in incoming_msg.lower():
        reviews = get_public_reviews()
        avis = "\n".join([f"{r[0]} ⭐{r[1]} – {r[2]}" for r in reviews])
        msg.body(f"📋 Avis récents :\n{avis}")
        return str(response)

    # Voir profil
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

    # Évaluation vol / hôtel / restaurant / fidélité
    review_type, rating, comment = parse_evaluation_message(incoming_msg)
    if review_type:
        points_map = {"vol": 10, "hôtel": 7, "restaurant": 5, "fidélité": 3}
        save_review(phone_hash, review_type, rating, comment)
        new_points = add_points(phone_hash, points_map.get(review_type, 0))
        msg.body(f"✅ Merci pour votre avis sur le {review_type} !\n⭐ Note : {rating}\n📝 Commentaire : {comment}\n\n🎉 Vous avez gagné {points_map[review_type]} points.\n🏆 Total : {new_points} points.")
        reviews = get_last_reviews(phone_hash)
        if reviews:
            msg.body("\n📋 Vos derniers avis :\n" + "\n".join([f"{r[0]} ⭐{r[1]} – {r[2]}" for r in reviews]))
            msg.body("🔗 Voir tous les avis")
        return str(response)

    # Requêtes : recherche d’hôtels
    hotel_match = re.search(r"h[oô]tel[s]? à ([\w\s\-]+)", incoming_msg, re.IGNORECASE)
    if hotel_match:
        city = hotel_match.group(1).strip()
        msg.body(search_hotels(city))
        return str(response)

    # Requêtes : restaurant
    resto_match = re.search(r"restaurant[s]? à ([\w\s\-]+)", incoming_msg, re.IGNORECASE)
    if resto_match:
        city = resto_match.group(1).strip()
        msg.body(search_restaurants(city))
        return str(response)

    # Requêtes : vol
    flight_match = re.search(r"vol de ([\w\s\-]+) vers ([\w\s\-]+)", incoming_msg, re.IGNORECASE)
    if flight_match:
        origin = flight_match.group(1).strip()
        dest = flight_match.group(2).strip()
        msg.body(search_flights(origin, dest))
        return str(response)

    # Requêtes : circuit touristique
    plan_match = re.search(r"plan à ([\w\s\-]+)", incoming_msg, re.IGNORECASE)
    if plan_match:
        city = plan_match.group(1).strip()
        msg.body(generate_travel_plan(city))
        return str(response)

    # Requêtes : bons plans
    bonplan_match = re.search(r"bons plans au ([\w\s\-]+)", incoming_msg, re.IGNORECASE)
    if bonplan_match:
        country = bonplan_match.group(1).strip()
        msg.body(get_travel_deals(country))
        return str(response)

    # Réclamation bagage
    if "bagage" in incoming_msg.lower() or "bagages" in incoming_msg.lower():
        msg.body("🧳 Pour une réclamation de bagage, veuillez contacter la compagnie avec votre numéro de vol et de bagage. Si vous avez besoin d’aide pour rédiger un message officiel, je peux vous assister.")
        return str(response)

    # Sinon : GPT
    try:
        reply = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Tu es Askely, un assistant de voyage multilingue."},
                {"role": "user", "content": incoming_msg}
            ],
            max_tokens=200
        )
        msg.body(reply.choices[0].message["content"])
    except:
        msg.body("❌ Erreur avec l’intelligence artificielle. Veuillez réessayer plus tard.")

    return str(response)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
