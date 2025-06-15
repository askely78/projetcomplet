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
        "⭐ *Évaluer un vol, hôtel, restaurant ou programme de fidélité* – Laisser un avis noté\n"
        "📋 *Voir tous les avis* – Lire les avis des autres utilisateurs\n"
        "👤 *Mon profil* – Voir vos points\n\n"
        "✍️ Pour évaluer, tapez :\n"
        "*évaluation hôtel: Nom, note: 4, avis: votre commentaire*\n"
        "*évaluation vol: Nom compagnie, note: 5, avis: commentaire*\n"
        "*évaluation restaurant: Nom, note: 3, avis: votre avis*\n"
        "*évaluation fidélité: Nom programme, note: 4, avis: ressenti*"
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

def parse_evaluation_message(message):
    patterns = {
        "vol": r"évaluation\s+vol[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
        "hôtel": r"évaluation\s+h[oô]tel[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
        "restaurant": r"évaluation\s+restaurant[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
        "fidélité": r"évaluation\s+fidélité[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
    }
    for type_, pattern in patterns.items():
        match = re.match(pattern, message, re.IGNORECASE)
        if match:
            return type_, int(match.group(2)), match.group(3)
    return None, None, None

@app.route("/webhook/whatsapp-webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    from_number = request.values.get("From", "")
    country = request.values.get("WaId", "")[:2]
    phone_hash = hash_phone_number(from_number)

    user_id, greeted = create_user_profile(from_number, country)
    response = MessagingResponse()
    msg = response.message()

    # Message d’accueil automatique à la première interaction
    if greeted == 0:
        welcome_message = (
            "🎉 *Bienvenue sur Askely !* 🎉\n\n"
            "Vous voulez noter votre vol, votre séjour dans un hôtel ou votre expérience dans un restaurant ?\n"
            "Vous serez récompensé par :\n"
            "✈️ 10 points pour les vols\n"
            "🏨 7 points pour les hôtels\n"
            "🍽️ 5 points pour les restaurants\n"
            "🎁 8 points pour les programmes de fidélité\n\n"
            "Envoyez un message comme :\n"
            "*évaluation hôtel: Riad Fès, note: 5, avis: service parfait !*\n\n"
            "Tapez *menu* pour voir tout ce que je peux faire."
        )
        msg.body(welcome_message)
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

    if "mon profil" in incoming_msg.lower() or "mes points" in incoming_msg.lower():
        conn = sqlite3.connect("askely.db")
        cursor = conn.cursor()
        cursor.execute("SELECT points, created_at FROM users WHERE phone_hash = ?", (phone_hash,))
        row = cursor.fetchone()
        conn.close()
        if row:
            points, created = row
            msg.body(f"👤 *Votre profil Askely*\n📅 Inscrit depuis : {created[:10]}\n🏆 Points : {points}")
        return str(response)

    if "voir tous les avis" in incoming_msg.lower():
        avis = get_public_reviews()
        textes = [f"{r[0]} ⭐{r[1]} – {r[2]}" for r in avis]
        msg.body("📋 *Avis récents :*\n" + "\n".join(textes))
        return str(response)

    # Traitement des évaluations
    review_type, rating, comment = parse_evaluation_message(incoming_msg)
    if review_type:
        points_map = {"vol": 10, "hôtel": 7, "restaurant": 5, "fidélité": 8}
        save_review(phone_hash, review_type, rating, comment)
        total_points = add_points(phone_hash, points_map[review_type])
        msg.body(f"✅ Merci pour votre avis sur le {review_type} !\n⭐ Note : {rating}\n📝 Commentaire : {comment}\n\n🎁 Vous avez gagné {points_map[review_type]} points.\n🏆 Total : {total_points} points.")
        derniers = get_last_reviews(phone_hash)
        if derniers:
            msg.body("📋 Vos derniers avis :\n" + "\n".join([f"{r[0]} ⭐{r[1]} – {r[2]}" for r in derniers]))
            msg.body("🔗 Voir tous les avis")
        return str(response)

    # Sinon, GPT libre
    try:
        completion = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Tu es Askely, un assistant de voyage multilingue, professionnel, clair et aimable."},
                {"role": "user", "content": incoming_msg}
            ],
            max_tokens=200
        )
        reply = completion.choices[0].message["content"]
        msg.body(reply)
    except:
        msg.body("❌ Erreur de traitement de votre demande. Réessayez plus tard.")

    return str(response)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
