from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
import openai
import requests
import os

app = Flask(__name__)

# Configuration des clés API
openai.api_key = os.getenv("OPENAI_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

@app.route('/')
def home():
    return "✅ Askely - Concierge IA (bagages, circuits, budget, météo, hôtels, restaurants)"

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
    message_lower = message.lower()

    # 🎯 Réponse automatique pour bagage perdu
    if any(word in message_lower for word in ["bagage", "valise", "aéroport", "perdu", "lost baggage"]):
        return (
            "🛄 *Assistance bagage perdu* :\n"
            "1. Rendez-vous au comptoir 'Lost & Found' de votre compagnie ou de l'aéroport.\n"
            "2. Remplissez un formulaire PIR (Property Irregularity Report).\n"
            "3. Conservez votre ticket de bagage et carte d’embarquement.\n"
            "4. Contactez leur service dans les 24h si aucune nouvelle.\n\n"
            "📨 *Exemple de réclamation* :\n"
            "Objet : Bagage perdu – Vol AT123 Casablanca → Paris\n"
            "Madame, Monsieur,\n"
            "Je vous contacte suite à la perte de ma valise enregistrée le 13 juin sur le vol AT123.\n"
            "Merci de votre assistance."
        )

    # Sinon, appel GPT pour conciergerie complète
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": (
                    "Tu es Askely, un assistant intelligent expert en conciergerie internationale.\n"
                    "Tu aides les utilisateurs à :\n"
                    "- Organiser des circuits touristiques (jours, lieux, activités)\n"
                    "- Élaborer un budget estimatif (hébergement, repas, transport, activités)\n"
                    "- Donner la météo actuelle d'une ville\n"
                    "- Suggérer des hôtels et restaurants\n"
                    "- Et en cas de bagage perdu, les guider (sauf si réponse automatique déjà envoyée).\n"
                    "Sois pratique, rapide et chaleureux."
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
