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
        CREATE TABLE IF NOT EXISTS avis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_hash TEXT,
            category TEXT,
            review TEXT,
            rating INTEGER,
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
        return existing_user[0]
    user_id = f"askely_{uuid.uuid4().hex[:8]}"
    cursor.execute("INSERT INTO users (id, phone_hash, country, language, points, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                   (user_id, phone_hash, country, language, 0, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()
    return user_id

def is_new_user(phone_number):
    phone_hash = hash_phone_number(phone_number)
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("SELECT created_at FROM users WHERE phone_hash = ?", (phone_hash,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return False
    try:
        created_time = datetime.fromisoformat(row[0])
        return (datetime.now(timezone.utc) - created_time).total_seconds() < 15
    except Exception:
        return False

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

def add_points_for_review(category):
    return {
        "vol": 50,
        "hotel": 40,
        "restaurant": 30,
        "fidelite": 20
    }.get(category.lower(), 0)

def add_review(phone_number, category, rating, review_text):
    phone_hash = hash_phone_number(phone_number)
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO avis (phone_hash, category, rating, review) VALUES (?, ?, ?, ?)",
                   (phone_hash, category, rating, review_text))
    cursor.execute("UPDATE users SET points = points + ? WHERE phone_hash = ?",
                   (add_points_for_review(category), phone_hash))
    cursor.execute("SELECT points FROM users WHERE phone_hash = ?", (phone_hash,))
    new_points = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return new_points

def get_last_reviews():
    conn = sqlite3.connect("askely.db")
    cursor = conn.cursor()
    cursor.execute("SELECT category, rating, review, created_at FROM avis ORDER BY created_at DESC LIMIT 3")
    rows = cursor.fetchall()
    conn.close()
    return "\n\n".join([f"⭐ {r[1]}/5 | {r[0].capitalize()} : {r[2]}" for r in rows])

@app.route("/webhook/whatsapp-webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    phone_number = request.values.get("From", "").replace("whatsapp:", "")
    country = request.values.get("WaId", "")[:2] if request.values.get("WaId") else "unknown"
    language = "auto"

    create_user_profile(phone_number, country, language)

    if is_new_user(phone_number):
        welcome = (
            "🎉 *Bienvenue sur Askely, votre assistant de voyage intelligent !* 🤖\n"
            "Voici ce que je peux faire pour vous :\n\n"
            "📍 *Recherches rapides* : hôtels, restaurants, vols, bagages, bons plans\n"
            "📝 *Gagnez des points* en tapant :\n"
            " - avis vol 5/5 très bon vol\n"
            " - avis hôtel 4/5 calme et propre\n"
            " - avis restaurant 3/5 bon mais lent\n"
            " - avis fidélité 5/5 programme utile\n\n"
            "👤 Tapez *mon profil* ou *mes points* pour consulter vos points\n"
            "📢 Tapez *tous les avis* pour voir les retours des autres utilisateurs"
        )
        resp = MessagingResponse()
        resp.message(welcome)
        return str(resp)

    msg_lower = corriger_message(incoming_msg.lower())

    if "mon profil" in msg_lower or "mes points" in msg_lower:
        phone_hash = hash_phone_number(phone_number)
        conn = sqlite3.connect("askely.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, points, created_at FROM users WHERE phone_hash = ?", (phone_hash,))
        data = cursor.fetchone()
        conn.close()
        if data:
            user_id, points, created_at = data
            msg = f"👤 *Votre Profil Askely*\n⭐ Points : {points}\n🗓️ Depuis : {created_at[:10]}"
        else:
            msg = "Aucun profil trouvé."
        resp = MessagingResponse()
        resp.message(msg)
        return str(resp)

    if "tous les avis" in msg_lower:
        avis = get_last_reviews()
        resp = MessagingResponse()
        resp.message(f"🗣️ *Derniers avis utilisateurs :*\n\n{avis}")
        return str(resp)

    match_avis = re.search(r"avis (vol|h[oô]tel|restaurant|fid[eé]lit[eé]) ?(\d)/5 (.+)", msg_lower)
    if match_avis:
        cat = match_avis.group(1)
        if "hôtel" in cat or "hô" in cat: cat = "hotel"
        if "fid" in cat: cat = "fidelite"
        rating = int(match_avis.group(2))
        text = match_avis.group(3)
        points = add_review(phone_number, cat, rating, text)
        resp = MessagingResponse()
        resp.message(f"✅ Avis enregistré pour {cat} ({rating}/5)\n🎁 +{add_points_for_review(cat)} points Askely ! Total : {points}\n📌 Tapez *mon profil* ou *tous les avis*.")
        return str(resp)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Tu es Askely, un assistant de voyage intelligent."},
                {"role": "user", "content": incoming_msg}
            ],
            max_tokens=300
        )
        answer = response.choices[0].message["content"]
    except Exception:
        answer = "⚠️ Erreur GPT. Réessayez plus tard."

    resp = MessagingResponse()
    resp.message(f"{answer}\n📌 Tapez *mon profil* pour consulter vos points.")
    return str(resp)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
