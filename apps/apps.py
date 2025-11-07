import os
import pyttsx3
import subprocess

# --- Voice engine setup ---
engine = pyttsx3.init()
engine.setProperty('rate', 175)
engine.setProperty('volume', 1.0)

def speak(text):
    print(f"JARVIS: {text}")
    engine.say(text)
    engine.runAndWait()

# --- Known special apps (Microsoft Store apps) ---
store_apps = {
    "whatsapp": "explorer.exe shell:appsFolder\\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App",
    "camera": "explorer.exe shell:appsFolder\\Microsoft.WindowsCamera_8wekyb3d8bbwe!App",
    "photos": "explorer.exe shell:appsFolder\\Microsoft.Windows.Photos_8wekyb3d8bbwe!App",
    "calculator": "explorer.exe shell:appsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
    "settings": "explorer.exe ms-settings:",
}

def open_any_app(app_name):
    app_name = app_name.lower()
    try:
        if app_name in store_apps:
            os.system(store_apps[app_name])
            speak(f"Opening {app_name}")
        else:
            subprocess.Popen(f"start {app_name}", shell=True)
            speak(f"Opening {app_name}")
    except Exception as e:
        speak(f"Sorry, I couldn’t open {app_name}. Error: {e}")

# --- Main program loop ---
if __name__ == "__main__":
    speak("Hello Sir, I am Jarvis. Type the app name you want to open.")
    while True:
        command = input("\nYou: ").lower().strip()

        if command == "":
            continue
        elif "open" in command:
            app_name = command.replace("open", "").strip()
            open_any_app(app_name)
        elif command in ["exit", "quit", "stop", "bye"]:
            speak("Goodbye Sir! Have a nice day.")
            break
        else:
            speak("Please type 'open' followed by the app name.")
