from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
import openai
import requests
import os

app = Flask(__name__)

# Configuration clés API
openai.api_key = os.getenv("OPENAI_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

@app.route('/')
def home():
    return "✅ Askely Agent is running (GPT-4, extraction de ville activée)."

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    message = data.get('message', '')
    return jsonify({"reply": handle_message(message)})

@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook():
    message = request.form.get('Body', '')
    sender = request.form.get('From', '')
    
    reply = handle_message(message)

    response = MessagingResponse()
    response.message(reply)
    return str(response)

def handle_message(message):
    message_lower = message.lower()
    city = extract_city(message)

    if "météo" in message_lower:
        return get_weather(city)
    elif "hôtel" in message_lower:
        return suggest_hotels(city)
    elif "restaurant" in message_lower:
        return suggest_restaurants(city)
    elif "circuit" in message_lower or "touristique" in message_lower:
        return suggest_tours(city)
    else:
        return ask_gpt(message)

def extract_city(message):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Tu es un assistant qui extrait le nom de la ville mentionnée dans une phrase."},
                {"role": "user", "content": f"Extrait la ville de ce message : '{message}'"}
            ]
        )
        return response.choices[0].message['content'].strip()
    except Exception:
        return "Marrakech"  # valeur par défaut

def get_weather(city):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric&lang=fr"
    response = requests.get(url).json()
    if response.get("cod") != 200:
        return f"❌ Impossible de récupérer la météo pour {city}."
    weather = response["weather"][0]["description"]
    temp = response["main"]["temp"]
    return f"🌤️ À {city}, il fait {temp}°C avec {weather}."

def suggest_hotels(city):
    return f"🏨 Suggestions d'hôtels à {city} : Hôtel Atlas, Riad Bahia, Hôtel Oasis."

def suggest_restaurants(city):
    return f"🍽️ Suggestions de restaurants à {city} : Dar Yacout, Le Tobsil, Al Fassia."

def suggest_tours(city):
    return f"🗺️ Circuits touristiques à {city} : Visite guidée de la médina, excursions dans les environs, marchés locaux."

def ask_gpt(message):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": message}]
        )
        return response.choices[0].message['content']
    except Exception as e:
        return f"❌ Erreur avec GPT : {str(e)}"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
