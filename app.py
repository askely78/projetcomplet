from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import openai
import os
import hashlib
import uuid
import sqlite3
from datetime import datetime, timezone

app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            phone_hash TEXT UNIQUE,
            state TEXT,
            temp_type TEXT,
            temp_rating TEXT,
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

def hash_phone_number(phone):
    return hashlib.sha256(phone.encode()).hexdigest()

# --- USER ---
def create_user(phone, country="unknown", language="unknown"):
    phone_hash = hash_phone_number(phone)
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE phone_hash = ?", (phone_hash,))
    user = cursor.fetchone()
    if not user:
        user_id = f"askely_{uuid.uuid4().hex[:8]}"
        cursor.execute("""
            INSERT INTO users (id, phone_hash, country, language, points, created_at, greeted, state)
            VALUES (?, ?, ?, ?, ?, ?, 0, '')
        """, (user_id, phone_hash, country, language, 0, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()

def get_user(phone_hash):
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE phone_hash = ?", (phone_hash,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_user_state(phone_hash, state=None, temp_type=None, temp_rating=None):
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users SET state = ?, temp_type = ?, temp_rating = ? WHERE phone_hash = ?
    """, (state or '', temp_type or '', temp_rating or '', phone_hash))
    conn.commit()
    conn.close()

def add_points(phone_hash, points):
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET points = points + ? WHERE phone_hash = ?", (points, phone_hash))
    cursor.execute("SELECT points FROM users WHERE phone_hash = ?", (phone_hash,))
    new_points = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return new_points

# --- REVIEW ---
def save_review(phone_hash, review_type, rating, comment):
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO reviews (phone_hash, type, rating, comment)
        VALUES (?, ?, ?, ?)
    """, (phone_hash, review_type, rating, comment))
    conn.commit()
    conn.close()

# --- UTIL ---
def get_main_menu():
    return (
        "🤖 Bienvenue sur Askely – Votre assistant voyage intelligent 🌍\n\n"
        "🎯 *Menu principal* :\n"
        "1. Évaluer un vol\n"
        "2. Évaluer un hôtel\n"
        "3. Évaluer un restaurant\n"
        "4. Évaluer un programme de fidélité\n"
        "5. Voir mes points\n"
        "6. Voir le menu\n\n"
        "Envoyez le *numéro* ou le *mot-clé* pour commencer."
    )

def get_review_points(review_type):
    return {
        "vol": 10,
        "hôtel": 7,
        "restaurant": 5,
        "fidélité": 8
    }.get(review_type, 0)

# --- WEBHOOK ---
@app.route("/webhook/whatsapp-webhook", methods=["POST"])
def webhook():
    incoming = request.values.get("Body", "").strip()
    phone = request.values.get("From", "")
    phone_hash = hash_phone_number(phone)
    create_user(phone)

    user = get_user(phone_hash)
    state, temp_type, temp_rating = user[2], user[3], user[4]

    response = MessagingResponse()
    msg = response.message()

    if incoming.lower() in ["menu", "6"]:
        update_user_state(phone_hash)
        msg.body(get_main_menu())
        return str(response)

    if incoming.lower() in ["5", "mes points"]:
        points = user[7]
        msg.body(f"🏆 Vous avez {points} points.")
        return str(response)

    if state == "waiting_type":
        if incoming.lower() in ["vol", "hôtel", "restaurant", "fidélité"]:
            update_user_state(phone_hash, "waiting_rating", incoming.lower())
            msg.body("Merci ! Quelle note (de 1 à 5) souhaitez-vous donner ?")
        else:
            msg.body("Veuillez choisir un type parmi : vol, hôtel, restaurant, fidélité.")
        return str(response)

    if state == "waiting_rating":
        if incoming.isdigit() and 1 <= int(incoming) <= 5:
            update_user_state(phone_hash, "waiting_comment", temp_type, incoming)
            msg.body("Merci ! Que souhaitez-vous écrire comme commentaire ?")
        else:
            msg.body("La note doit être un nombre entre 1 et 5.")
        return str(response)

    if state == "waiting_comment":
        points = get_review_points(temp_type)
        save_review(phone_hash, temp_type, int(temp_rating), incoming)
        total_points = add_points(phone_hash, points)
        update_user_state(phone_hash)
        msg.body(f"✅ Merci pour votre avis sur le {temp_type} !\n🎉 Vous avez gagné {points} points.\n🏆 Total : {total_points} points.")
        return str(response)

    if incoming.lower() in ["1", "vol"]:
        update_user_state(phone_hash, "waiting_rating", "vol")
        msg.body("Très bien ! Quelle note (1 à 5) souhaitez-vous donner pour ce vol ?")
        return str(response)

    if incoming.lower() in ["2", "hôtel"]:
        update_user_state(phone_hash, "waiting_rating", "hôtel")
        msg.body("Très bien ! Quelle note (1 à 5) souhaitez-vous donner pour cet hôtel ?")
        return str(response)

    if incoming.lower() in ["3", "restaurant"]:
        update_user_state(phone_hash, "waiting_rating", "restaurant")
        msg.body("Très bien ! Quelle note (1 à 5) souhaitez-vous donner pour ce restaurant ?")
        return str(response)

    if incoming.lower() in ["4", "fidélité"]:
        update_user_state(phone_hash, "waiting_rating", "fidélité")
        msg.body("Très bien ! Quelle note (1 à 5) souhaitez-vous donner pour ce programme de fidélité ?")
        return str(response)

    # GPT libre
    try:
        reply = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Tu es Askely, un assistant de voyage."},
                {"role": "user", "content": incoming}
            ],
            max_tokens=200
        )
        msg.body(reply.choices[0].message["content"])
    except:
        msg.body("❌ Je n’ai pas pu répondre pour le moment. Réessayez plus tard.")

    return str(response)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
