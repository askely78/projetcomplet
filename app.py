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
    return "✅ Askely - Concierge IA mondial (voyage, circuits, budget, bagages)"

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    message = data.get('message', '')
    return jsonify({"reply": askely_reply(message)})

@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook():
    message = request.form.get('Body', '')
    sender = request.form.get('From', '')
    reply = askely_reply(message)

    response = MessagingResponse()
    response.message(reply)
    return str(response)

def askely_reply(message):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": (
                    "Tu es Askely, un agent intelligent spécialisé en conciergerie de voyage. "
                    "Tu aides les utilisateurs à organiser leurs séjours dans n'importe quelle ville du monde. "
                    "Tu proposes des circuits touristiques détaillés (jours, lieux, activités), des budgets estimatifs (hébergement, repas, transport, activités), "
                    "des recommandations d'hôtels et restaurants, la météo locale. "
                    "Tu assistes aussi les utilisateurs en cas de bagages perdus à l'aéroport : tu expliques les étapes à suivre, "
                    "proposes un exemple de réclamation, donnes les bons réflexes et adresses utiles."
                )},
                {"role": "user", "content": message}
            ]
        )
        return response.choices[0].message['content']
    except Exception as e:
        return f"❌ Erreur avec GPT : {str(e)}"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
