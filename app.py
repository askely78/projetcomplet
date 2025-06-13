from flask import Flask, request, jsonify
import openai
import requests
import os

app = Flask(__name__)

# Clés API
openai.api_key = os.getenv("OPENAI_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

@app.route('/')
def home():
    return "✅ Askely Agent is running."

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    message = data.get('message', '')
    return jsonify({"reply": handle_message(message)})

@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook():
    data = request.get_json()
    message = data.get('message', '')
    return jsonify({"reply": handle_message(message)})

def handle_message(message):
    message = message.lower()

    if "météo" in message:
        return get_weather("Marrakech")
    elif "hôtel" in message:
        return suggest_hotels("Marrakech")
    elif "restaurant" in message:
        return suggest_restaurants("Marrakech")
    else:
        return ask_gpt(message)

def get_weather(city):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric&lang=fr"
    response = requests.get(url).json()
    if response.get("cod") != 200:
        return "❌ Je ne peux pas récupérer la météo pour cette ville."
    weather = response["weather"][0]["description"]
    temp = response["main"]["temp"]
    return f"🌤️ À {city}, il fait {temp}°C avec {weather}."

def suggest_hotels(city):
    return f"🏨 Suggestions d'hôtels à {city} : Hôtel Atlas, Riad Bahia, Hôtel Oasis."

def suggest_restaurants(city):
    return f"🍽️ Suggestions de restaurants à {city} : Dar Yacout, Le Tobsil, Al Fassia."

def ask_gpt(message):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": message}]
        )
        return response.choices[0].message['content']
    except Exception as e:
        return f"❌ Erreur avec l'intelligence artificielle : {str(e)}"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
