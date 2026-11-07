"""theme.py - die EINE Farbpalette von ReaperPy (Hauptfenster, Werkzeug-Fenster, Update-Dialog, Splash).

Alle Oberflaechen-Dateien holen ihre Farben von hier (gui.py und tools_common.py reichen sie unter den bekannten Namen weiter).
Neue Farben bitte NUR hier aendern; hartkodierte "#rrggbb"-Werte in den Oberflaechen-Dateien sind zu vermeiden.

Aufbau: dunkles Blau in vier Stufen (BG < BG_BAR < BG_CARD < BG_CARD_HVR), sichtbare Rahmen, ein kraeftiger Akzent (Mint) und
klar getrennte Statusfarben (OK gruen, WARN gelb, ERROR rot).  Die Textfarben haben genug Abstand zum Hintergrund (Kontrast >= 4.5).
"""

# Flaechen (dunkel -> hell)
BG = "#060a14"            # Fensterhintergrund
BG_BAR = "#0b1428"        # Leisten, Tabellenkoepfe, gesperrte Felder
BG_CARD = "#101d36"       # Karten, Eingabefelder, Tabellen
BG_CARD_HVR = "#1a2f56"   # Karte / Knopf unter der Maus
BG_CARD_ON = "#0b3326"    # aktive Karte (gruen getoent)
BG_LOG = "#03060f"        # Protokoll- und Textfelder (tiefster Ton)
SELECT = "#1d4f91"        # markierte Zeile / Auswahl
BTN_HVR = "#254580"       # zweitrangige Knoepfe unter der Maus

# Rahmen
BORDER = "#243a66"
BORDER_HVR = "#3f64a8"

# Akzent
ACCENT = "#00ffc8"
ACCENT_DIM = "#00c79c"
ACCENT_HI = "#7dffe3"     # Glanzkante, Knopf-Hover
ACCENT_BG = BG_CARD_ON
INK_ON_ACCENT = "#04110d"  # Schrift auf Akzentflaechen

# Schrift
TEXT = "#f2f7ff"
TEXT_DIM = "#93a9d3"
TEXT_DIM2 = "#5b7099"

# Status
OK = "#3dff8c"
WARN = "#ffc21a"
ERROR = "#ff6690"

# Platzhalter-Farben fuer Bibliothekskarten ohne Icon (kraeftig, aber dunkel genug fuer weisse Schrift)
COVER_COLORS = ("#0f4a52", "#2d3a7a", "#5a2f78", "#0f5c4c", "#6b3f2a", "#1f5a85", "#6a5a14", "#2f6a3a")
