# Partie 1 : importations, base de données, utilisateurs, points
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
def search_hotels(city):
    hotels = [f"{city} Palace", f"Riad {city}", f"Dar Atlas {city}", f"Luxury Stay {city}", f"Hotel Central {city}"]
    return "\n".join([f"🏨 Hôtels à {city} :"] + [f"{i+1}. {h}" for i, h in enumerate(hotels)])

def search_restaurants(city):
    restos = [f"{city} Gourmet", f"Bistro {city}", f"Chez {city}", f"La Table {city}", f"Café Medina"]
    return "\n".join([f"🍽️ Restaurants à {city} :"] + [f"{i+1}. {r}" for i, r in enumerate(restos)])

def search_flights(origin, destination):
    return (
        f"✈️ Vols disponibles de {origin} vers {destination} :\n"
        f"1. Royal Air Maroc – Départ 10:00\n"
        f"2. Air France – Départ 13:30\n"
        f"3. Qatar Airways – Départ 18:15"
    )

def generate_travel_plan(city):
    return (
        f"🗺️ Plan touristique à {city} :\n"
        f"Jour 1 : Médina et monuments historiques\n"
        f"Jour 2 : Souks et gastronomie locale\n"
        f"Jour 3 : Excursion nature autour de {city}"
    )

def get_travel_deals(country):
    return (
        f"💡 Bons plans au {country} :\n"
        f"- Réductions dans les riads locaux\n"
        f"- Street food typique à petit prix\n"
        f"- Offres sur les excursions en groupe"
    )

def get_welcome_message():
    return (
        "👋 Bienvenue sur Askely !\n\n"
        "Vous voulez noter votre vol, votre séjour dans un hôtel ou votre expérience dans un restaurant ?\n"
        "Vous serez récompensé par :\n"
        "✈️ 10 points pour les vols\n"
        "🏨 7 points pour les hôtels\n"
        "🍽️ 5 points pour les restaurants\n"
        "🎫 8 points pour les programmes de fidélité\n\n"
        "Ou vous avez une demande qui concerne votre voyage ? Cela n’est pas récompensé.\n"
        "Commencez l’expérience dès maintenant et gagnez des points à chaque avis ! 🎉\n\n"
        "Tapez *menu* pour voir les options disponibles."
    )

def get_main_menu():
    return (
        "📋 *Menu Askely – Concierge IA* 🌍\n\n"
        "🏨 Hôtels à [ville]\n"
        "🍽️ Restaurants à [ville]\n"
        "✈️ Vol de [ville A] vers [ville B]\n"
        "🧳 Réclamation bagage\n"
        "🗺️ Plan à [ville]\n"
        "💡 Bons plans au [pays]\n"
        "⭐ Évaluer un vol / hôtel / restaurant / fidélité\n"
        "📋 Voir tous les avis\n"
        "👤 Mon profil\n"
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
    except:
        return msg

# Dialogue guidé
def start_guided_review(type_name):
    return f"📝 D’accord ! Tu veux évaluer un {type_name}. Donne-moi la *note de 1 à 5 étoiles*."

def continue_guided_review(note):
    return "Parfait ! Maintenant, écris un *commentaire court* sur ton expérience."

def get_points_for_type(type_name):
    return {"vol": 10, "hôtel": 7, "restaurant": 5, "fidélité": 8}.get(type_name.lower(), 0)

# Message parser (si l’utilisateur écrit l’avis en une phrase libre)
def parse_evaluation_message(message):
    patterns = {
        "vol": r"évaluation\s+vol[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
        "hôtel": r"évaluation\s+h[oô]tel[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
        "restaurant": r"évaluation\s+restaurant[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
        "fidélité": r"évaluation\s+fidélité[:\-]?\s*(.*?),\s*note[:\-]?\s*(\d),\s*avis[:\-]?\s*(.+)",
    }
    for review_type, pattern in patterns.items():
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return review_type, int(match.group(2)), match.group(3)
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

    if greeted == 0:
        msg.body(get_welcome_message())
        mark_greeted(phone_hash)
        return str(response)

    incoming_msg = corriger_message(incoming_msg.lower())

    if incoming_msg in ["menu", "aide"]:
        msg.body(get_main_menu())
        return str(response)

    if "mon profil" in incoming_msg or "mes points" in incoming_msg:
        conn = sqlite3.connect("askely.db")
        cursor = conn.cursor()
        cursor.execute("SELECT points, created_at FROM users WHERE phone_hash = ?", (phone_hash,))
        row = cursor.fetchone()
        conn.close()
        msg.body(f"👤 *Profil Askely*\n📅 Inscription : {row[1][:10]}\n🏆 Points : {row[0]}")
        return str(response)

    if "voir tous les avis" in incoming_msg:
        reviews = get_public_reviews()
        avis = "\n".join([f"{r[0]} ⭐{r[1]} – {r[2]}" for r in reviews])
        msg.body(f"📋 Avis récents :\n{avis}")
        return str(response)

    # Dialogue guidé déclenché
    guided_match = re.search(r"(je veux évaluer|je veux noter) (un|une)?\s*(vol|h[oô]tel|restaurant|fidélité)", incoming_msg)
    if guided_match:
        type_eval = guided_match.group(3).replace("ô", "o").lower()
        if type_eval == "hotel":
            type_eval = "hôtel"
        return str(MessagingResponse().message(start_guided_review(type_eval)))

    rating_match = re.match(r"note[:\-]?\s*(\d)", incoming_msg)
    if rating_match:
        note = int(rating_match.group(1))
        return str(MessagingResponse().message(continue_guided_review(note)))

    full_eval_match = re.match(r"(vol|hôtel|restaurant|fidélité)\s+\d\s+.+", incoming_msg)
    if full_eval_match:
        parts = incoming_msg.split(" ", 2)
        review_type = parts[0]
        rating = int(parts[1])
        comment = parts[2]
        points = get_points_for_type(review_type)
        save_review(phone_hash, review_type, rating, comment)
        total = add_points(phone_hash, points)
        msg.body(f"✅ Avis enregistré : {review_type} ⭐{rating} – {comment}\n🎉 +{points} points (total : {total})")
        reviews = get_last_reviews(phone_hash)
        if reviews:
            msg.body("📋 Vos derniers avis :\n" + "\n".join([f"{r[0]} ⭐{r[1]} – {r[2]}" for r in reviews]) + "\n🔗 Voir tous les avis")
        return str(response)

    # Recherche hôtels
    hotel_match = re.search(r"h[oô]tel[s]? à ([\w\s\-]+)", incoming_msg)
    if hotel_match:
        city = hotel_match.group(1).strip()
        msg.body(search_hotels(city))
        return str(response)

    # Recherche restaurants
    resto_match = re.search(r"restaurant[s]? à ([\w\s\-]+)", incoming_msg)
    if resto_match:
        city = resto_match.group(1).strip()
        msg.body(search_restaurants(city))
        return str(response)

    # Vols
    flight_match = re.search(r"vol de ([\w\s\-]+) vers ([\w\s\-]+)", incoming_msg)
    if flight_match:
        origin = flight_match.group(1).strip()
        dest = flight_match.group(2).strip()
        msg.body(search_flights(origin, dest))
        return str(response)

    # Plan touristique
    plan_match = re.search(r"plan à ([\w\s\-]+)", incoming_msg)
    if plan_match:
        city = plan_match.group(1).strip()
        msg.body(generate_travel_plan(city))
        return str(response)

    # Bons plans
    bonplan_match = re.search(r"bons plans au ([\w\s\-]+)", incoming_msg)
    if bonplan_match:
        country = bonplan_match.group(1).strip()
        msg.body(get_travel_deals(country))
        return str(response)

    # Bagage
    if "bagage" in incoming_msg:
        msg.body("🧳 Pour une réclamation de bagage, indiquez la compagnie et le numéro de vol. Je peux rédiger un message pour vous.")
        return str(response)

    # GPT fallback
    try:
        reply = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Tu es Askely, assistant de voyage."},
                {"role": "user", "content": incoming_msg}
            ],
            max_tokens=200
        )
        msg.body(reply.choices[0].message["content"])
    except:
        msg.body("❌ Erreur OpenAI. Réessayez plus tard.")

    return str(response)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(debug=True, host="0.0.0.0", port=port)
