
from flask import Flask, request, jsonify
import openai
import requests
import os

app = Flask(__name__)

openai.api_key = os.getenv("OPENAI_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

@app.route('/')
def home():
    return "Askely MVP is running."

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    message = data.get('message', '')

    if "météo" in message.lower():
        return jsonify({"reply": get_weather("Marrakech")})
    elif "hôtel" in message.lower():
        return jsonify({"reply": suggest_hotels("Marrakech")})
    elif "restaurant" in message.lower():
        return jsonify({"reply": suggest_restaurants("Marrakech")})
    else:
        return jsonify({"reply": ask_gpt(message)})

def get_weather(city):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric&lang=fr"
    response = requests.get(url).json()
    if response.get("cod") != 200:
        return "Je n'ai pas pu obtenir la météo pour cette ville."
    weather = response["weather"][0]["description"]
    temp = response["main"]["temp"]
    return f"🌤️ Il fait actuellement {temp}°C à {city} avec {weather}."

def suggest_hotels(city):
    return f"Voici quelques hôtels à {city} : Hôtel Atlas, Riad Bahia, et Hôtel Oasis."

def suggest_restaurants(city):
    return f"Voici quelques restaurants à {city} : Dar Yacout, Le Tobsil, Al Fassia."

def ask_gpt(message):
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": message}]
    )
    return response.choices[0].message['content']

if __name__ == '__main__':
    app.run(debug=True, port=5000)
