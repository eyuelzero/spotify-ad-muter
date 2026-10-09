# Spotify Ad Muter

A lightweight cross-platform utility (Windows & Linux) that automatically mutes Spotify ads and unmutes music afterward.

## Features

- Automatically detects Spotify ads:
  - **Windows**: Window title detection (pygetwindow)
  - **Linux**: DBus MPRIS2 metadata tracking (with window title fallback)
- Mutes Spotify during ads:
  - **Windows**: Windows Core Audio API (pycaw)
  - **Linux**: PulseAudio / PipeWire (`pactl`)
- Unmutes when music resumes
- System tray support
- Editable config file
- Lightweight and simple

## Screenshot

![App Screenshot](screenshots/app.png)

---

## Installation

### 1. Install Python

Download Python from:
https://www.python.org/downloads/

### 2. Install dependencies

**Windows:**
```bash
pip install -r requirements.txt
```

**Linux (Arch / CachyOS):**
```bash
sudo pacman -S python-dbus tk python-pystray
pip install -r requirements.txt
```

**Linux (Debian / Ubuntu):**
```bash
sudo apt install python3-dbus python3-tk
pip install -r requirements.txt
```

### 3. Run the app

```bash
python spotify_ad_muter.py
```

---

## Build Executable / Binary

**Windows (EXE):**
```bash
pyinstaller --onefile --windowed --icon=icon.ico spotify_ad_muter.py
```

**Linux:**
```bash
pyinstaller --onefile --windowed spotify_ad_muter.py
```

---

## Config File

The app automatically creates:

- **Windows:** `AppData/Roaming/SpotifyAdMuter/config.json`
- **Linux:** `~/.config/SpotifyAdMuter/config.json`

You can edit the blocked titles list manually.


---

## Disclaimer

This project does not modify Spotify or bypass advertisements.
It only mutes the Spotify audio session locally.

---

## License

MIT