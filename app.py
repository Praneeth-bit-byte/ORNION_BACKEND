import os
import re
import time
import threading
import uuid
from datetime import datetime
import tempfile

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from pymongo import MongoClient
import requests as py_requests
from dotenv import load_dotenv
from gtts import gTTS

# =========================================================
#               LOAD ENVIRONMENT VARIABLES
# =========================================================
load_dotenv()

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
PERPLEXITY_API_URL = os.getenv("PERPLEXITY_API_URL", "https://api.perplexity.ai/chat/completions")
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "JarvisDB")
CONV_COLLECTION = os.getenv("CONV_COLLECTION", "conversations")

# =========================================================
#                   FLASK APP SETUP
# =========================================================
app = Flask(__name__, template_folder="templates")
CORS(app)

# =========================================================
#                   MONGODB CONNECTION
# =========================================================
try:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    # Create collection if not existing
    if CONV_COLLECTION not in db.list_collection_names():
        db.create_collection(CONV_COLLECTION)

    conversations = db[CONV_COLLECTION]
    print("✅ MongoDB connected successfully.")
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")
    conversations = None

# =========================================================
#               VOICE ENGINE (gTTS)
# =========================================================
def speak(text: str) -> None:
    """Convert text to speech using Google TTS (optional)."""
    print(f"ORNION: {text}")
    try:
        tts = gTTS(text=text, lang='en', slow=False, tld='com')
        with tempfile.NamedTemporaryFile(delete=True, suffix=".mp3") as fp:
            tts.save(fp.name)
            # Audio playback skipped on production server
    except Exception as e:
        print(f"[Speech Error] {e}")

# =========================================================
#                PERPLEXITY API HANDLER
# =========================================================
def ask_perplexity(user_input: str) -> str:
    """Send message to Perplexity API and return response."""
    try:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "sonar-pro",
            "messages": [{"role": "user", "content": user_input}],
            "stream": False
        }

        response = py_requests.post(PERPLEXITY_API_URL, json=data, headers=headers, timeout=20)
        response.raise_for_status()
        response_data = response.json()

        if "choices" in response_data and response_data["choices"]:
            reply = response_data["choices"][0]["message"]["content"]
        else:
            reply = "I'm sorry, I couldn't understand that."

        reply = re.sub(r"[^\w\s,.?!:;\'\"-]", "", reply)
        return reply

    except Exception as e:
        print("❌ Perplexity API error:", e)
        return "Sorry, I couldn't connect to my knowledge system right now."

# =========================================================
#                      FLASK ROUTES
# =========================================================
@app.route("/")
def index():
    """Serve frontend."""
    return render_template("index.html")


@app.route('/ask', methods=['POST'])
def ask():
    """Main query endpoint for ORNION."""
    user_input = request.json.get('message', '')
    start = time.time()

    reply = ask_perplexity(user_input)
    print("Perplexity took", round(time.time() - start, 2), "seconds")

    # Speak the reply (optional, non-blocking)
    threading.Thread(target=speak, args=(reply,), daemon=True).start()

    return jsonify({'input': user_input, 'reply': reply})


# =========================================================
#              MONGODB SESSION MANAGEMENT
# =========================================================
@app.route('/start_session', methods=['POST'])
def start_session():
    """Create new conversation session safely."""
    try:
        if conversations is None:
            return jsonify({"error": "Database not connected"}), 500

        session_id = str(uuid.uuid4())
        new_session = {
            "session_id": session_id,
            "created_at": datetime.utcnow(),
            "messages": []
        }

        conversations.insert_one(new_session)
        print(f"🟢 New session created: {session_id}")
        return jsonify({"session_id": session_id}), 200

    except Exception as e:
        print(f"❌ Error creating session: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/save_message', methods=['POST'])
def save_message():
    """Save user or ORNION message into conversation."""
    try:
        if conversations is None:
            return jsonify({"error": "Database unavailable"}), 500

        data = request.json or {}
        session_id = data.get("session_id")
        speaker = data.get("speaker")
        text = data.get("text")

        if not session_id or not text or not speaker:
            return jsonify({"error": "Missing fields"}), 400

        result = conversations.update_one(
            {"session_id": session_id},
            {"$push": {"messages": {
                "speaker": speaker,
                "text": text,
                "timestamp": datetime.utcnow()
            }}}
        )

        if result.modified_count == 0:
            return jsonify({"error": "Session not found"}), 404

        print(f"💬 Message saved in session {session_id}: {speaker} → {text[:50]}")
        return jsonify({"status": "saved"}), 200

    except Exception as e:
        print(f"❌ Error saving message: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/get_history/<session_id>', methods=['GET'])
def get_history(session_id):
    """Retrieve stored chat history for a session."""
    try:
        if conversations is None:
            return jsonify({"error": "Database unavailable"}), 500

        convo = conversations.find_one({"session_id": session_id}, {"_id": 0})
        if convo:
            return jsonify(convo), 200
        return jsonify({"error": "Session not found"}), 404

    except Exception as e:
        print(f"❌ Error getting history: {e}")
        return jsonify({"error": str(e)}), 500


# =========================================================
#                 RUN FLASK (PRODUCTION)
# =========================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
