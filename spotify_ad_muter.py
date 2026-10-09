# =============================================================================
# Spotify Ad Muter — Cross-Platform (Windows + Linux)
# =============================================================================
#
# Original project: Windows-only ad muter using pycaw + pygetwindow.
#
# This PR adds Linux support while keeping all existing Windows code unchanged.
# Linux support is implemented using:
#
#   - Ad detection:  Spotify's DBus MPRIS2 interface (org.mpris.MediaPlayer2)
#                    Spotify marks ads with a trackid of "spotify:ad:*", which
#                    is far more reliable than window title matching.
#                    Falls back to xdotool window title matching if DBus fails.
#
#   - Mute/unmute:   pactl (PulseAudio/PipeWire CLI) to mute Spotify's
#                    audio sink input by application name.
#
#   - Config path:   ~/.config/SpotifyAdMuter/config.json (XDG standard)
#                    instead of %APPDATA%\SpotifyAdMuter\config.json
#
# Linux dependencies (install via pacman on Arch/CachyOS):
#   sudo pacman -S python-dbus tk python-pystray
#   Optional fallback: sudo pacman -S xdotool
#
# No existing Windows behaviour has been modified.
# =============================================================================

import tkinter as tk
from tkinter import ttk
import threading
import time
import subprocess
import os
import json
import platform
import pystray
from PIL import Image, ImageDraw

# ── Platform detection (added for Linux support) ─────────────────────────────
# Used throughout to branch between Windows (original) and Linux (new) paths.
IS_LINUX = platform.system() == "Linux"
IS_WINDOWS = platform.system() == "Windows"

running = False
tray_icon = None

# ── Config path ───────────────────────────────────────────────────────────────
# Windows (unchanged): %APPDATA%\SpotifyAdMuter\config.json
# Linux   (added):     ~/.config/SpotifyAdMuter/config.json  (XDG convention)
if IS_WINDOWS:
    APP_DIR = os.path.join(os.getenv("APPDATA", ""), "SpotifyAdMuter")
else:
    APP_DIR = os.path.join(os.path.expanduser("~"), ".config", "SpotifyAdMuter")

CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULT_CONFIG = {
    "blocked_titles": [
        "listen to music, ad-free.",
        "advertisement",
        "spotify free",
        "spotify premium"
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


# ── Ad detection ──────────────────────────────────────────────────────────────

# [ADDED FOR LINUX]
# On Linux, Spotify exposes its current playback state over DBus using the
# MPRIS2 standard (org.mpris.MediaPlayer2). When a Spotify ad is playing,
# the track metadata contains a trackid in the format "spotify:ad:<id>",
# which is a reliable, first-party signal — much more precise than window
# title matching. A secondary fallback uses xdotool to read the window title
# the same way the original Windows code does.
def is_ad_playing_linux():
    # --- Method 1: DBus MPRIS2 (primary, most reliable) ---
    # Requires: python-dbus  (sudo pacman -S python-dbus)
    # Spotify must be running for this bus name to be available.
    try:
        import dbus
        bus = dbus.SessionBus()
        player = bus.get_object(
            "org.mpris.MediaPlayer2.spotify",
            "/org/mpris/MediaPlayer2"
        )
        props = dbus.Interface(player, "org.freedesktop.DBus.Properties")
        metadata = props.Get("org.mpris.MediaPlayer2.Player", "Metadata")

        track_id = str(metadata.get("mpris:trackid", ""))
        artist = metadata.get("xesam:artist", [""])
        title = str(metadata.get("xesam:title", "")).lower()

        # Spotify consistently marks ads with a trackid of "spotify:ad:XXXX".
        # This is the most reliable detection method.
        if "spotify:ad:" in track_id:
            return True

        # Secondary check: ads often have no artist listed.
        # Cross-reference with the blocked_titles list from config as a guard.
        if not artist or (len(artist) == 1 and str(artist[0]).strip() == ""):
            blocked = config.get("blocked_titles", [])
            for blocked_title in blocked:
                if blocked_title.lower() in title:
                    return True

        return False

    except Exception:
        # DBus unavailable (Spotify not open, dbus-python not installed, etc.)
        # Fall through to the window title fallback below.
        pass

    # --- Method 2: Window title fallback via xdotool ---
    # Requires: xdotool  (sudo pacman -S xdotool)
    # Uses the same blocked_titles logic as the original Windows implementation.
    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", "Spotify"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0 and result.stdout.strip():
            win_id = result.stdout.strip().split("\n")[0]
            name_result = subprocess.run(
                ["xdotool", "getwindowname", win_id],
                capture_output=True, text=True, timeout=2
            )
            title = name_result.stdout.strip().lower()
            blocked = config.get("blocked_titles", [])
            for blocked_title in blocked:
                if blocked_title.lower() in title:
                    return True
    except Exception:
        pass

    return False


# [UNCHANGED — original Windows ad detection]
# Reads all open window titles and checks them against the blocked_titles list
# in config.json. Uses pygetwindow which is a Windows-only library.
def is_ad_playing_windows():
    try:
        import pygetwindow as gw
        blocked_titles = config.get("blocked_titles", [])
        for title in gw.getAllTitles():
            lower_title = title.lower()
            for blocked in blocked_titles:
                if blocked.lower() in lower_title:
                    return True
        return False
    except Exception:
        return False


# [ADDED FOR LINUX] Dispatcher: routes to the correct platform implementation.
def is_ad_playing():
    if IS_LINUX:
        return is_ad_playing_linux()
    return is_ad_playing_windows()


# ── Mute / unmute ─────────────────────────────────────────────────────────────

# [ADDED FOR LINUX]
# On Linux, audio sessions are managed by PulseAudio or PipeWire (which
# exposes a PulseAudio-compatible interface). The `pactl` CLI tool is used
# to find Spotify's sink input by its application.name property and toggle
# its mute state — equivalent to what pycaw does on Windows.
def mute_spotify_linux(mute: bool):
    # Requires: pactl  (part of libpulse, pre-installed on most Linux desktops)
    try:
        # List all active audio sink inputs to find Spotify's
        result = subprocess.run(
            ["pactl", "list", "sink-inputs"],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.split("\n")
        current_sink_input = None
        for line in lines:
            line = line.strip()
            if line.startswith("Sink Input #"):
                # Track the current sink input index as we scan
                current_sink_input = line.split("#")[1]
            elif "application.name" in line.lower() and "spotify" in line.lower():
                # Found Spotify's sink input — apply mute/unmute
                if current_sink_input:
                    subprocess.run(
                        ["pactl", "set-sink-input-mute",
                         current_sink_input, "1" if mute else "0"],
                        timeout=3
                    )
    except Exception:
        pass


# [UNCHANGED — original Windows mute implementation]
# Uses pycaw (Windows Core Audio API wrapper) to find the Spotify.exe audio
# session and toggle its mute state via the SimpleAudioVolume interface.
def mute_spotify_windows(mute: bool):
    try:
        from pycaw.pycaw import AudioUtilities
        sessions = AudioUtilities.GetAllSessions()
        for session in sessions:
            try:
                process = session.Process
                if process and process.name().lower() == "spotify.exe":
                    volume = session.SimpleAudioVolume
                    volume.SetMute(1 if mute else 0, None)
            except Exception:
                pass
    except Exception:
        pass


# [ADDED FOR LINUX] Dispatcher: routes to the correct platform implementation.
def mute_spotify(mute: bool = True):
    if IS_LINUX:
        mute_spotify_linux(mute)
    else:
        mute_spotify_windows(mute)


# ── Monitor loop ──────────────────────────────────────────────────────────────

def monitor_ads(status_label):
    global running
    ad_active = False

    while running:
        try:
            is_ad = is_ad_playing()

            if is_ad and not ad_active:
                mute_spotify(True)
                ad_active = True
                status_label.config(text="Ad detected — Spotify muted 🔇")

            elif not is_ad and ad_active:
                mute_spotify(False)
                ad_active = False
                status_label.config(text="Music playing — Spotify unmuted 🎵")

            elif not is_ad:
                status_label.config(text="Monitoring Spotify...")

        except Exception as e:
            status_label.config(text=f"Error: {str(e)}")

        time.sleep(1)


# ── GUI controls ──────────────────────────────────────────────────────────────

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
        pystray.MenuItem("Open", show_window),
        pystray.MenuItem("Quit", quit_app)
    )
    tray_icon = pystray.Icon(
        "SpotifyAdMuter",
        create_tray_image(),
        "Spotify Ad Muter",
        menu
    )
    threading.Thread(target=tray_icon.run, daemon=True).start()


# ── GUI layout ────────────────────────────────────────────────────────────────

root = tk.Tk()
root.title("Spotify Ad Muter")
root.geometry("360x240")
root.resizable(True, True)
root.protocol("WM_DELETE_WINDOW", minimize_to_tray)

frame = ttk.Frame(root, padding=20)
frame.pack(fill="both", expand=True)

title = ttk.Label(
    frame,
    text="Spotify Ad Muter",
    font=("Segoe UI", 16, "bold")
)
title.pack(pady=(0, 15))

platform_label = ttk.Label(
    frame,
    text=f"Running on {platform.system()}",
    font=("Segoe UI", 8),
    foreground="gray"
)
platform_label.pack(pady=(0, 5))

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