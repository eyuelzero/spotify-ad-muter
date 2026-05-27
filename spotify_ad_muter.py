import tkinter as tk
from tkinter import ttk
import threading
import time
import pygetwindow as gw
from pycaw.pycaw import AudioUtilities
import os
import json
import pystray
from PIL import Image, ImageDraw

running = False
tray_icon = None

APP_DIR = os.path.join(
    os.getenv("APPDATA"),
    "SpotifyAdMuter"
)

CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULT_CONFIG = {
    "blocked_titles": [
        "listen to music, ad-free.",
        "advertisement",
        "spotify free"
    ]
}


def ensure_config():
    os.makedirs(APP_DIR, exist_ok=True)

    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)

    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


config = ensure_config()


def get_spotify_window_title():
    blocked_titles = config.get("blocked_titles", [])

    all_windows = gw.getAllTitles()

    for title in all_windows:
        lower_title = title.lower()

        for blocked in blocked_titles:
            if blocked.lower() in lower_title:
                return True

    return False


def get_spotify_session():
    sessions = AudioUtilities.GetAllSessions()

    for session in sessions:
        try:
            process = session.Process

            if process and process.name().lower() == "spotify.exe":
                return session

        except:
            pass

    return None


def mute_spotify(mute=True):
    session = get_spotify_session()

    if session:
        volume = session.SimpleAudioVolume
        volume.SetMute(1 if mute else 0, None)


def monitor_ads(status_label):
    global running

    ad_active = False

    while running:
        try:
            is_ad = get_spotify_window_title()

            if is_ad and not ad_active:
                mute_spotify(True)
                ad_active = True
                status_label.config(
                    text="Ad detected — Spotify muted"
                )

            elif not is_ad and ad_active:
                mute_spotify(False)
                ad_active = False
                status_label.config(
                    text="Music playing — Spotify unmuted"
                )

            elif not is_ad:
                status_label.config(
                    text="Monitoring Spotify..."
                )

        except Exception as e:
            status_label.config(
                text=f"Error: {str(e)}"
            )

        time.sleep(1)


def start_monitoring(status_label):
    global running

    if not running:
        running = True

        thread = threading.Thread(
            target=monitor_ads,
            args=(status_label,),
            daemon=True
        )

        thread.start()

        status_label.config(text="Monitoring started")


def stop_monitoring(status_label):
    global running

    running = False
    mute_spotify(False)

    status_label.config(text="Stopped")


def on_close():
    stop_monitoring(status_label)

    if tray_icon:
        tray_icon.stop()

    root.destroy()


def show_window(icon=None, item=None):
    root.after(0, root.deiconify)


def quit_app(icon=None, item=None):
    on_close()


def minimize_to_tray():
    root.withdraw()


def create_tray_image():
    image = Image.new("RGB", (64, 64), color=(30, 215, 96))

    draw = ImageDraw.Draw(image)
    draw.ellipse((16, 16, 48, 48), fill=(0, 0, 0))

    return image


def setup_tray():
    global tray_icon

    menu = pystray.Menu(
        pystray.MenuItem(
            "Open",
            show_window
        ),
        pystray.MenuItem(
            "Quit",
            quit_app
        )
    )

    tray_icon = pystray.Icon(
        "SpotifyAdMuter",
        create_tray_image(),
        "Spotify Ad Muter",
        menu
    )

    threading.Thread(
        target=tray_icon.run,
        daemon=True
    ).start()


# GUI

root = tk.Tk()

root.title("Spotify Ad Muter")
root.geometry("360x240")
root.resizable(True, True)

root.protocol(
    "WM_DELETE_WINDOW",
    minimize_to_tray
)

frame = ttk.Frame(root, padding=20)
frame.pack(fill="both", expand=True)

title = ttk.Label(
    frame,
    text="Spotify Ad Muter",
    font=("Segoe UI", 16, "bold")
)

title.pack(pady=(0, 15))

status_label = ttk.Label(
    frame,
    text="Ready",
    font=("Segoe UI", 10)
)

status_label.pack(pady=(0, 15))

start_button = ttk.Button(
    frame,
    text="Start",
    command=lambda: start_monitoring(status_label)
)

start_button.pack(fill="x", pady=5)

stop_button = ttk.Button(
    frame,
    text="Stop",
    command=lambda: stop_monitoring(status_label)
)

stop_button.pack(fill="x", pady=5)

quit_button = ttk.Button(
    frame,
    text="Quit",
    command=on_close
)

quit_button.pack(fill="x", pady=5)

setup_tray()
start_monitoring(status_label)
root.mainloop()