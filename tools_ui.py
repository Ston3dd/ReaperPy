"""tools_ui.py - kleine Oberflaechen-Helfer fuer das Werkzeug-Fenster (Einsteiger-Komfort).

    Tooltip / tip()             Hilfe-Blase beim Darueberfahren (kurze Verzoegerung, verschwindet beim Klicken)
    TERMS / find_term()         Fachbegriffe mit Erklaerung (DE + EN); decorate() haengt sie automatisch an passende Labels/Knoepfe
    NET_BUTTONS / set_net_state()  Knoepfe, die eine Konsolenverbindung brauchen: ohne Verbindung abgegraut + Erklaerung im Tooltip
    paint_steps()               Ergebnis von VERBINDUNG PRUEFEN farbig (gruen / rot / gelb) in ein Text-Widget schreiben
    decorate(window)            alles auf einmal auf den Widget-Baum anwenden (idempotent, vom Werkzeug-Fenster aufgerufen)

Die Texte sind hier zweisprachig abgelegt (de, en) - sie brauchen keine Eintraege in tools_i18n_en.
"""
import tkinter as tk

import tools_i18n
from tools_common import (BG_CARD, BG_CARD_HVR, BORDER_HVR, ERROR, FONT_TEXT, FONT_TEXT_B, OK, TEXT, TEXT_DIM,
                          TEXT_DIM2, WARN)

TEXT_WIDGETS = ("Label", "Button", "Checkbutton", "Radiobutton")


def _lang():
    try:
        return tools_i18n.lang()
    except Exception:  # noqa: BLE001
        return "de"


def _pick(pair):
    de, en = pair
    return en if _lang() == "en" else de


def de_text(w):
    """Deutscher Originaltext eines Widgets (auch wenn gerade Englisch angezeigt wird)."""
    try:
        store = w.__dict__.get("_i18n") or {}
        if "text" in store and isinstance(store["text"][0], str):
            return store["text"][0]
        t = w.cget("text")
        return t if isinstance(t, str) else ""
    except Exception:  # noqa: BLE001
        return ""


def walk(root):
    stack = [root]
    while stack:
        w = stack.pop()
        yield w
        try:
            stack.extend(w.winfo_children())
        except Exception:  # noqa: BLE001
            pass


# ==================================================================
# Tooltip
# ==================================================================
class Tooltip:
    """Hilfe-Blase.  `text` ist ein String oder eine Funktion ohne Argumente (wird erst beim Anzeigen ausgewertet -
    so stimmt die Sprache und der Verbindungs-Hinweis immer)."""
    DELAY = 450

    def __init__(self, widget, text):
        self.widget, self.text = widget, text
        self._job = None
        self._win = None
        for seq, fn in (("<Enter>", self._enter), ("<Leave>", self._leave), ("<ButtonPress>", self._leave),
                        ("<Destroy>", self._leave)):
            widget.bind(seq, fn, add="+")

    def current(self):
        t = self.text() if callable(self.text) else self.text
        return (t or "").strip()

    def _enter(self, _e=None):
        self._cancel()
        try:
            self._job = self.widget.after(self.DELAY, self._show)
        except Exception:  # noqa: BLE001
            self._job = None

    def _leave(self, _e=None):
        self._cancel()
        self.hide()

    def _cancel(self):
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except Exception:  # noqa: BLE001
                pass
            self._job = None

    def _show(self):
        self._job = None
        text = self.current()
        if not text or self._win is not None:
            return
        try:
            w = self.widget
            x = w.winfo_rootx() + 12
            y = w.winfo_rooty() + w.winfo_height() + 4
            x = max(0, min(x, w.winfo_screenwidth() - 400))
            tw = tk.Toplevel(w)
            tw.wm_overrideredirect(True)
            tw.configure(bg=BORDER_HVR)
            tk.Label(tw, text=text, justify="left", bg=BG_CARD_HVR, fg=TEXT, font=FONT_TEXT, wraplength=380,
                     padx=8, pady=8).pack(padx=2, pady=2)
            tw.wm_geometry(f"+{x}+{y}")
            self._win = tw
        except Exception:  # noqa: BLE001
            self._win = None

    def hide(self):
        if self._win is not None:
            try:
                self._win.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._win = None


def tip(widget, text):
    """Tooltip an ein Widget haengen (merkt sich ihn am Widget; ein zweiter Aufruf tauscht nur den Text)."""
    t = widget.__dict__.get("_tooltip")
    if t is None:
        widget._tooltip = Tooltip(widget, text)
    else:
        t.text = text
    return widget._tooltip


# ==================================================================
# Fachbegriffe
# ==================================================================
# (Text exakt oder Anfang, ist_Anfang, deutsch, englisch).  Der Text ist der DEUTSCHE Beschriftungstext des Widgets.
TERMS = [
    ("OFFSET (ab Image-Base)", False,
     "Abstand der Stelle vom Anfang des Spielprogramms (der Image-Basis). Weil er vom Programmanfang aus gezählt wird, "
     "stimmt er auch nach einem Neustart des Spiels noch.",
     "Distance of the spot from the start of the game program (the image base). Because it is counted from the "
     "start of the program, it is still right after the game restarts."),
    ("OriginReturn", True,
     "Wie viele Bytes der Hook überschreibt. Dort läuft das Spiel nach deiner Cave weiter. Leer lassen: ReaperPy "
     "rechnet es aus den Originalbytes aus (ganze Befehle, mindestens 8).",
     "How many bytes the hook overwrites. That is where the game continues after your cave. Leave it empty: "
     "ReaperPy works it out from the original bytes (whole instructions, at least 8)."),
    ("SIGNATUR", True,
     "Ein Byte-Muster, an dem der Cheat seine Stelle nach einem Spiel-Update wiederfindet. Beim Speichern erzeugt "
     "ReaperPy sie selbst.",
     "A byte pattern the cheat uses to find its place again after a game update. ReaperPy creates it for you "
     "when you save."),
    ("MUSTER", False,
     "Byte-Muster (AOB). ?? steht für ein beliebiges Byte. Damit sucht ReaperPy eine Stelle im Spiel, auch wenn sie "
     "sich nach einem Update verschoben hat.",
     "Byte pattern (AOB). ?? stands for any byte. ReaperPy uses it to find a spot in the game even if it has moved "
     "after an update."),
    ("CAVE-CODE", True,
     "Eine Code-Cave ist freier Platz im Spiel, in dem dein eigener kleiner Code läuft. Der Hook springt hinein, "
     "der Code arbeitet, und jmp OriginReturn geht zurück.",
     "A code cave is free space in the game where your own small piece of code runs. The hook jumps into it, "
     "the code does its work, and jmp OriginReturn goes back."),
    ("HOOK-LÄNGE", False,
     "So viele Bytes überschreibt der Hook an der Stelle. Ein Hook ist ein Sprung in deinen eigenen Code.",
     "This many bytes the hook overwrites at the spot. A hook is a jump into your own code."),
    ("Hook-Bytes wildcarden", False,
     "Ersetzt die überschriebenen Bytes in der Signatur durch ??, damit sie auch passt, wenn der Cheat schon aktiv ist.",
     "Replaces the overwritten bytes in the signature with ??, so it still matches while the cheat is active."),
    ("NOP", False,
     "NOP ist ein Befehl, der nichts tut. Ersetzt du einen Befehl durch NOPs, kann er nichts mehr verändern - "
     "so hältst du zum Beispiel einen Wert fest.",
     "NOP is an instruction that does nothing. If you replace an instruction with NOPs it can no longer change "
     "anything - that is how you keep a value from changing, for example."),
    ("SNAPSHOT", False,
     "Merkt sich den jetzigen Zustand des Speichers, damit du ihn später mit dem neuen Zustand vergleichen kannst.",
     "Remembers the current state of the memory so you can compare it with a later state."),
    ("VERGLEICH", False,
     "Zeigt, welche Bytes sich seit dem Snapshot geändert haben.",
     "Shows which bytes have changed since the snapshot."),
    ("UPDATE-SCAN", False,
     "Sucht jeden Patch nach einem Spiel-Update über seine Signatur neu und nennt den neuen Offset.",
     "Searches every patch again after a game update using its signature and reports the new offset."),
    ("ZIELADRESSE", False,
     "Die Adresse, deren Wert du auch nach einem Neustart wiederfinden willst. Die Pointer-Suche sucht einen festen Weg dorthin.",
     "The address whose value you want to find again after a restart. The pointer search looks for a fixed path to it."),
    ("TIEFE", False,
     "Wie viele Zeiger hintereinander verfolgt werden. Mehr Tiefe findet mehr Wege, dauert aber länger.",
     "How many pointers are followed one after another. More depth finds more paths but takes longer."),
    ("MAX. OFFSET", False,
     "Wie weit ein Zeiger von seinem Ziel entfernt sein darf. Größer = mehr Treffer, aber auch mehr Zufallstreffer.",
     "How far a pointer may be from its target. Larger = more hits, but also more chance hits."),
    ("MODUL-BASIS", False,
     "Anfang des Spielcodes im Speicher. Static-Offsets werden von hier aus gezählt.",
     "Start of the game code in memory. Static offsets are counted from here."),
    ("STATIC-OFFSET", False,
     "Fester Abstand vom Anfang des Spielcodes - ändert sich bei einem Neustart nicht.",
     "Fixed distance from the start of the game code - does not change on a restart."),
    ("BREAKPOINT @", False,
     "Hält das Spiel an, sobald dieser Befehl ausgeführt wird.",
     "Stops the game as soon as this instruction is executed."),
    ("WATCHPOINT @", False,
     "Hält das Spiel an, sobald jemand auf diese Adresse schreibt (oder liest). So findest du den Befehl, der einen Wert ändert.",
     "Stops the game as soon as something writes to (or reads) this address. That is how you find the instruction that changes a value."),
    ("WER SCHREIBT?", False,
     "Findet den Befehl im Spiel, der diesen Wert ändert. Aus ihm baust du den Cheat.",
     "Finds the instruction in the game that changes this value. You build the cheat from it."),
    ("ATTACH", False,
     "Hängt den Debugger an das Spiel. Das Spiel läuft weiter, bis ein Haltepunkt trifft.",
     "Attaches the debugger to the game. The game keeps running until a breakpoint hits."),
    ("ERWEITERTE OPTIONEN", False,
     "Zeigt Patch-Art, OriginReturn, Cave-Code und Signatur, damit du sie selbst bestimmen kannst.",
     "Shows the patch type, OriginReturn, cave code and signature so you can set them yourself."),
]

NO_NET = ("Nicht mit der Konsole verbunden. Klicke im Hauptfenster auf VERBINDEN - dieser Knopf wird dann von selbst frei.",
          "Not connected to the console. Click CONNECT in the main window - this button then unlocks by itself.")


def find_term(de):
    """Passenden Eintrag zu einem deutschen Beschriftungstext suchen -> (de, en) oder None."""
    t = (de or "").strip()
    if not t:
        return None
    for key, prefix, d, e in TERMS:
        if t == key or (prefix and t.startswith(key)):
            return (d, e)
    return None


# ==================================================================
# Knoepfe, die eine Konsolenverbindung brauchen
# ==================================================================
# Nur Knoepfe, die sicher live auf die PS5 zugreifen.  Dateiarbeit (LADEN, SPEICHERN, KONVERTIEREN, EXPORT ...) und
# VERBINDUNG PRUEFEN bleiben immer frei - sie funktionieren auch ohne Verbindung.
NET_BUTTONS = frozenset({
    # Speicher / Disassembler
    "LESEN", "SCHREIBEN", "MAPS", "DISASM", "FOLGEN", "DATEI → SPEICHER…", "NOP", "ÄNDERN…",
    "XREFS AUF ADRESSE", "ALS CAVE-HOOK",
    # Cheat-Editor / Signaturen
    "TEST AN", "TEST AUS", "ERZEUGEN", "UPDATE-SCAN", "SIGNATUREN ERZEUGEN (fehlende)", "VERGLEICH", "SERVER-SCAN",
    # Wert suchen / Assistent / Pointer
    "ERSTER SCAN", "NÄCHSTER SCAN", "⚡ SCHNELL-SCAN (Konsole)", "WER SCHREIBT?", "WERT SETZEN", "❄ FREEZE",
    "→ POINTER-SCAN", "SELBSTTEST", "REGIONEN-BERICHT", "WERTE AKTUALISIEREN",
    "SUCHEN", "EINGRENZEN", "GEFALLEN", "GESTIEGEN", "GLEICH GEBLIEBEN", "PRESET…",
    "1) KARTE ERSTELLEN", "2) PFADE SUCHEN", "3) PRÜFEN (neues Ziel)",
    # Debugger
    "ATTACH", "DETACH", "BEOBACHTEN", "STOPP", "▶ WEITER", "REGISTER", "THREADS", "STACK", "STACK-SCAN",
    "⤴ STEP OUT", "⤵ STEP", "⤼ STEP OVER", "■ ANHALTEN",
    # Live im Spiel (Unreal / Unity)
    "LIVE AUFLÖSEN", "TABELLE LIVE LESEN", "TABELLEN IM SPIEL LISTEN", "NATIVE ADR. (live)", "UFUNKTION AUFRUFEN (live)",
    "LIVE FINDEN",
})


def console_ready(app):
    """True, wenn das Hauptfenster mit der PS5 verbunden ist (dieselbe Regel wie beim Verbinden der Werkzeuge)."""
    try:
        be = app.backend
        return bool(getattr(be, "client", None)) and getattr(be, "pid", None) is not None
    except Exception:  # noqa: BLE001
        return False


def _tip_text(w):
    parts = []
    if w.__dict__.get("_net_blocked"):
        parts.append(_pick(NO_NET))
    term = w.__dict__.get("_term")
    if term:
        parts.append(_pick(term))
    return "\n\n".join(parts)


def set_net_state(root, connected):
    """Knoepfe aus NET_BUTTONS sperren/freigeben.  Es wird nur freigegeben, was WIR gesperrt haben (ein Knopf, den ein Tab
    selbst gesperrt hat - zum Beispiel STOPP ohne laufenden Job -, bleibt, wie der Tab ihn gesetzt hat).  -> Anzahl Aenderungen"""
    changed = 0
    for w in walk(root):
        try:
            if w.winfo_class() != "Button":
                continue
        except Exception:  # noqa: BLE001
            continue
        if de_text(w) not in NET_BUTTONS:
            continue
        try:
            blocked = w.__dict__.get("_net_blocked", False)
            if not connected and not blocked and str(w.cget("state")) == "normal":
                w.configure(state="disabled")
                w._net_blocked = True
                changed += 1
            elif connected and blocked:
                w.configure(state="normal")
                w._net_blocked = False
                changed += 1
            if w.__dict__.get("_tooltip") is None:
                tip(w, lambda w=w: _tip_text(w))
        except Exception:  # noqa: BLE001
            continue
    return changed


def attach_terms(root):
    """Fachbegriff-Tooltips an passende Labels/Knoepfe/Haken haengen.  -> Anzahl neu angehaengter."""
    n = 0
    for w in walk(root):
        try:
            if w.winfo_class() not in TEXT_WIDGETS or w.__dict__.get("_term"):
                continue
            term = find_term(de_text(w))
            if not term:
                continue
            w._term = term
            if w.__dict__.get("_tooltip") is None:
                tip(w, lambda w=w: _tip_text(w))
            if w.winfo_class() == "Label":
                w.configure(cursor="question_arrow")           # zeigt: hier gibt es eine Erklaerung
            n += 1
        except Exception:  # noqa: BLE001
            continue
    return n


def decorate(window):
    """Tooltips + Sperrzustand auf das ganze Fenster anwenden (idempotent)."""
    attach_terms(window)
    set_net_state(window, console_ready(getattr(window, "app", None)))


def help_chip(parent, term_key, bg=None):
    """Kleines "?" neben einem Begriff - Tooltip mit der Erklaerung aus TERMS (term_key = deutscher Begriff)."""
    term = find_term(term_key)
    lbl = tk.Label(parent, text="?", bg=bg or BG_CARD, fg=TEXT_DIM, font=FONT_TEXT_B, cursor="question_arrow",
                   padx=4, pady=0)
    if term:
        lbl._term = term
        tip(lbl, lambda w=lbl: _tip_text(w))
    return lbl


# ==================================================================
# Farbiges Pruefergebnis
# ==================================================================
_MARK = {"ok": "✓", "fail": "✗", "warn": "!", "info": "•", "skip": "–"}
TAGS = {"ok": dict(foreground=OK), "fail": dict(foreground=ERROR), "warn": dict(foreground=WARN),
        "info": dict(foreground=TEXT_DIM), "skip": dict(foreground=TEXT_DIM2), "title": dict(foreground=TEXT),
        "title_skip": dict(foreground=TEXT_DIM2),
        "detail": dict(foreground=TEXT, lmargin1=22, lmargin2=22, spacing3=3)}


def _rows(steps):
    """[(Zeichen-Tag, Zeichen, Titel, Detail)] - Details nur bei Fehlern, Warnungen und Hinweisen."""
    out = []
    for s in steps:
        detail = s.detail if s.state in ("fail", "warn", "info") else ""
        out.append((s.state, _MARK.get(s.state, "•"), s.title, detail))
    return out


def paint_lines(txt, lines):
    """lines: [(tag, zeichen, titel, detail)] in ein (gesperrtes) Text-Widget schreiben."""
    txt.configure(state="normal")
    txt.delete("1.0", "end")
    for name, kw in TAGS.items():
        txt.tag_configure(name, **kw)
    est = 0
    for tag, mark, title, detail in lines:
        txt.insert("end", mark + "  ", (tag,))
        txt.insert("end", title + "\n", ("title_skip" if tag == "skip" else "title",))
        est += 1
        if detail:
            txt.insert("end", detail + "\n", ("detail",))
            est += max(1, -(-len(detail) // 105))
    txt.configure(height=max(1, min(14, est)), state="disabled")
    return est


def paint_steps(txt, steps):
    """Ergebnis von conncheck.diagnose farbig anzeigen."""
    return paint_lines(txt, _rows(steps))


def paint_message(txt, kind, message):
    """Eine einzelne Meldung (z. B. "Pruefe ...", Fehler) in der Farbe von `kind` anzeigen."""
    return paint_lines(txt, [(kind, _MARK.get(kind, "•"), message, "")])
