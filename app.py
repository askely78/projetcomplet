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

WELCOME_MESSAGE = (
    "🤖 *Bienvenue sur Askely* – Votre concierge intelligent 🌍\n\n"
    "Vous voulez noter votre vol, votre séjour dans un hôtel ou votre expérience dans un restaurant ?\n"
    "Vous serez récompensé par :\n"
    "✈️ 10 points pour les vols\n"
    "🏨 7 points pour les hôtels\n"
    "🍽️ 5 points pour les restaurants\n"
    "💠 3 points pour les programmes de fidélité\n\n"
    "Ou vous avez une demande qui concerne votre voyage ?\n"
    "Cela n’est pas récompensé.\n\n"
    "Commencez l’expérience dès maintenant et gagnez des points à chaque avis ! 🎉\n\n"
    "📋 Tapez *menu* pour voir tout ce que je peux faire pour vous."
)

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
            first_seen INTEGER DEFAULT 0
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
    existing_user = cursor.fetchone()
    if existing_user:
        conn.close()
        return existing_user[0], existing_user[6]
    user_id = f"askely_{uuid.uuid4().hex[:8]}"
    cursor.execute("INSERT INTO users (id, phone_hash, country, language, points, created_at, first_seen) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (user_id, phone_hash, country, language, 0, datetime.now(timezone.utc).isoformat(), 0))
    conn.commit()
    conn.close()
    return user_id, 0

def set_first_seen(phone_hash):
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET first_seen = 1 WHERE phone_hash = ?", (phone_hash,))
    conn.commit()
    conn.close()

@app.route("/webhook/whatsapp-webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    phone_number = request.values.get("From", "").replace("whatsapp:", "")
    country = request.values.get("WaId", "")[:2] if request.values.get("WaId") else "unknown"
    language = "auto"

    user_id, first_seen = create_user_profile(phone_number, country, language)
    phone_hash = hash_phone_number(phone_number)

    resp = MessagingResponse()

    if not first_seen:
        set_first_seen(phone_hash)
        resp.message(WELCOME_MESSAGE)
        return str(resp)

    # ... autres traitements (avis, menu, points, etc.) ...

    resp.message("🧠 Je suis Askely, posez-moi votre question ou tapez *menu*.")
    return str(resp)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
