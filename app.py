import os
import re
import time
import threading
import subprocess
import uuid
from datetime import datetime

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from pymongo import MongoClient
import requests as py_requests
from dotenv import load_dotenv
import pyttsx3
from pystray import Icon, Menu, MenuItem as item
from PIL import Image

# =========================================================
#               LOAD ENVIRONMENT VARIABLES
# =========================================================
load_dotenv()

# --- Voice engine setup ---
engine = pyttsx3.init()
engine.setProperty('rate', 175)
engine.setProperty('volume', 1.0)

def speak(text: str) -> None:
    """Convert text to speech using pyttsx3."""
    print(f"JARVIS: {text}")
    engine.say(text)
    engine.runAndWait()


# =========================================================
#                 CONFIGURATION
# =========================================================
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
PERPLEXITY_API_URL = os.getenv("PERPLEXITY_API_URL", "https://api.perplexity.ai/chat/completions")
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "JarvisDB")
CONV_COLLECTION = os.getenv("CONV_COLLECTION", "Conversations")


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
#                WINDOWS APP LAUNCHING
# =========================================================
store_apps = {
    "whatsapp": "explorer.exe shell:appsFolder\\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App",
    "camera": "explorer.exe shell:appsFolder\\Microsoft.WindowsCamera_8wekyb3d8bbwe!App",
    "photos": "explorer.exe shell:appsFolder\\Microsoft.Windows.Photos_8wekyb3d8bbwe!App",
    "calculator": "explorer.exe shell:appsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
    "settings": "explorer.exe ms-settings:"
}

def open_any_app(app_name: str) -> str:
    """Open Windows apps or executables by name."""
    app_name = app_name.lower()
    try:
        if app_name in store_apps:
            os.system(store_apps[app_name])
            speak(f"Opening {app_name}.")
            return f"Opening {app_name}."
        else:
            subprocess.Popen(f"start {app_name}", shell=True)
            speak(f"Opening {app_name}.")
            return f"Opening {app_name}."
    except Exception as e:
        speak(f"Sorry, I couldn’t open {app_name}. Error: {e}")
        return f"Sorry, I couldn’t open {app_name}. Error: {e}"


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
    """Main query endpoint for JARVIS."""
    user_input = request.json.get('message', '')
    start = time.time()

    # Open app command
    match = re.match(r'open\s+([a-zA-Z0-9 _-]+)', user_input.lower())
    if match:
        app_name = match.group(1).strip()
        reply = open_any_app(app_name)
        return jsonify({'input': user_input, 'reply': reply})

    # Otherwise use AI backend
    reply = ask_perplexity(user_input)
    print("Perplexity took", round(time.time() - start, 2), "seconds")
    return jsonify({'input': user_input, 'reply': reply})


@app.route("/wake", methods=["POST"])
def wake():
    """Handle wake-up signal from frontend."""
    return jsonify({"status": "awake"})


@app.route("/sleep", methods=["POST"])
def sleep():
    """Handle sleep signal from frontend."""
    return jsonify({"status": "sleep"})


# =========================================================
#              DESKTOP TRIGGER INTEGRATION
# =========================================================
desktop_trigger_state = {"listen": False, "stop": False}

@app.route('/trigger_listen', methods=["POST", "GET"])
def trigger_listen():
    if desktop_trigger_state["listen"]:
        desktop_trigger_state["listen"] = False
        return jsonify({"status": "started_listening"})
    return jsonify({"status": "idle"})

@app.route('/trigger_stop', methods=["POST", "GET"])
def trigger_stop():
    if desktop_trigger_state["stop"]:
        desktop_trigger_state["stop"] = False
        return jsonify({"status": "stopped_speaking"})
    return jsonify({"status": "idle"})


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
    """Save user or JARVIS message into conversation."""
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
#                 SYSTEM TRAY INTEGRATION
# =========================================================
def quit_app(icon, item):
    """Exit JARVIS system tray."""
    print("🛑 Exiting Jarvis...")
    os._exit(0)

def start_listening():
    print("🎤 Listening started (desktop signal)")
    desktop_trigger_state["listen"] = True

def stop_speaking():
    print("🔇 Speaking stopped (desktop signal)")
    desktop_trigger_state["stop"] = True

def run_flask():
    app.run(debug=False, use_reloader=False)

def start_tray():
    """Start system tray icon (Windows only)."""
    try:
        icon_image = Image.open("jarvis.png")
        icon = Icon("Jarvis", icon_image, "Jarvis Assistant", menu=Menu(item('Quit', quit_app)))
        icon.run()
    except Exception as e:
        print("⚠️ Tray initialization failed:", e)
        run_flask()


# =========================================================
#                      ENTRY POINT
# =========================================================
if __name__ == "__main__":
    # Run Flask in a background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Run system tray in main thread
    start_tray()
