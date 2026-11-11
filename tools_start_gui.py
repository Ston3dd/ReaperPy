"""tools_start_gui.py - Tab "START": Einstieg fuer Anfaenger (drei Schritte, grosse Knoepfe, Klartext).

Zeigt, ob die PS5 verbunden ist und welches Spiel/welche Codes gerade offen sind, und fuehrt per Knopfdruck zu den
einfachen Werkzeugen.  Alles Spezielle liegt im Tab FORTGESCHRITTEN.
"""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

import conncheck
import tools_i18n
import tools_ui
from tools_common import (ACCENT, BG, BG_CARD, ERROR, FONT_HEAD, FONT_LABEL, FONT_TEXT, OK, TEXT, TEXT_DIM, TEXT_DIM2, WARN, BaseTab,
                          button)

# Ampel-Farben der Statuszeilen
STATE_COLOR = {"ok": OK, "fail": ERROR, "warn": WARN, "info": TEXT_DIM2}

STEPS = [
    ("1", "Spiel verbinden",
     "Starte dein Spiel und lade den Spielstand. Trage im Hauptfenster die IP deiner PS5 ein und klicke oben auf "
     "VERBINDEN. Wenn das Spiel Codes hat, erscheinen sie dort automatisch. Klappt es nicht? VERBINDUNG PRÜFEN "
     "(unten) sagt dir in Klartext, woran es liegt.",
     "HAUPTFENSTER ZEIGEN", "show_main"),
    ("2", "Wert finden und Cheat bauen",
     "Du siehst im Spiel eine Zahl (z. B. 100 Leben oder 5000 Gold)? Der ASSISTENT führt dich in vier Schritten: "
     "Zahl suchen, eingrenzen, den Befehl finden, der sie ändert, und daraus einen Cheat bauen - ohne Assembler-Kenntnisse.",
     "ZUM ASSISTENTEN", "assist_tab"),
    ("3", "Cheat speichern",
     "Der fertige Cheat liegt im Reiter CHEATS BEARBEITEN. Gib ihm einen Namen, probiere ihn mit TEST AN und "
     "speichere ihn. Für dein Cheat-Menü exportierst du ihn im Hauptfenster über GOLDHEN-JSON.",
     "ZU CHEATS BEARBEITEN", "t_cheat"),
]
EXTRAS = [
    ("Wert von Hand suchen", "Für Kenner: der volle Cheat-Sucher mit allen Suchmodi und Speicherbereichen.",
     "ZU WERT SUCHEN", "scan_tab"),
    ("Anleitungen", "Schritt-für-Schritt-Erklärungen zu allen Werkzeugen - zum Lesen und Suchen, in deiner Sprache.",
     "ANLEITUNGEN ÖFFNEN", "howto"),
    ("Unreal-Engine-Spiel: Items als Trainer", "Alle Items eines Unreal-Spiels automatisch finden und als fertigen "
     "Trainer speichern - in drei Klicks.", "ZU ITEMS", "items_tab"),
    ("Unity-Spiel: Items als Trainer", "Alle Items eines Unity-Spiels automatisch finden und als fertigen Trainer "
     "speichern - in drei Klicks (Reiter UNITY, Unterreiter ITEMS).", "ZU UNITY ▸ ITEMS", "unity_items_tab"),
    ("Unreal-Engine-Spiel: Leben, Gold, Erfahrung, Munition", "Wichtige Werte als fertige Patches - in drei Klicks "
     "(Reiter UNREAL, Unterreiter WERTE).", "ZU WERTE", "values_tab"),
    ("Unity-Spiel: Leben, Gold, Erfahrung, Munition", "Wichtige Werte als fertige Patches - in drei Klicks "
     "(Reiter UNITY, Unterreiter SCHNELL).", "ZU UNITY ▸ SCHNELL", "values_tab_unity"),
    ("Unreal-Engine-Spiel: Spezialfälle", "Tabellen, Funktionen und Werte von Hand ansehen.",
     "UE-ENTDECKER ÖFFNEN", "discover_tab"),
    ("Unity-Spiel: Spezialfälle", "Felder, Methoden und Namen von Hand ansehen und ändern.",
     "ZU UNITY ▸ MANUELL", "unity_tab"),
    ("Mehr Werkzeuge", "Speicher, Disassembler, Debugger, Pointer, Skripte und Co. für Fortgeschrittene.",
     "FORTGESCHRITTEN ÖFFNEN", "adv_frame"),
]
HINT = "Tipp: Mit der rechten Maustaste auf Listen und Felder klicken zeigt passende Aktionen (Kopieren, Öffnen, ...)."


class StartTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.v_status = tk.StringVar(value="")
        self.v_check = tk.StringVar(value="")
        self.buttons = {}
        self._checking = False
        self._check_steps = None            # letztes Ergebnis der Pruefung
        tk.Label(self, text="▸  WILLKOMMEN BEI REAPERPY", bg=BG, fg=ACCENT, font=FONT_HEAD).pack(anchor="w", padx=16, pady=(16, 2))
        tk.Label(self, text="In drei Schritten zum eigenen Cheat - ohne Vorkenntnisse.", bg=BG, fg=TEXT_DIM,
                 font=FONT_TEXT).pack(anchor="w", padx=16)
        box = tk.Frame(self, bg=BG_CARD)
        box.pack(fill="x", padx=16, pady=12)
        self._dots = []                                     # (Punkt, Text) je Statuszeile
        for _i in range(2):
            line = tk.Frame(box, bg=BG_CARD)
            line.pack(fill="x", padx=12, pady=(8 if _i == 0 else 2, 0))
            dot = tk.Label(line, text="●", bg=BG_CARD, fg=TEXT_DIM2, font=FONT_TEXT)
            dot.pack(side="left")
            txt = tk.Label(line, text="", bg=BG_CARD, fg=TEXT, font=FONT_TEXT, justify="left", anchor="w")
            txt.pack(side="left", padx=8, fill="x", expand=True)
            self._dots.append((dot, txt))
        row = tk.Frame(box, bg=BG_CARD)
        row.pack(fill="x", padx=12, pady=(8, 4))
        self.btn_check = button(row, "VERBINDUNG PRÜFEN", self.run_check, accent=True)
        self.btn_check.pack(side="left")
        tk.Label(row, text="Prüft IP, PS5, Payload und Spiel - ohne etwas zu verändern.", bg=BG_CARD, fg=TEXT_DIM,
                 font=FONT_TEXT).pack(side="left", padx=12)
        self.txt_check = tk.Text(box, height=1, wrap="word", bg=BG_CARD, fg=TEXT, font=FONT_TEXT, relief="flat",
                                 bd=0, highlightthickness=0, cursor="arrow", padx=0, pady=0)
        self.txt_check.pack(fill="x", padx=12, pady=(0, 8))
        self.txt_check.configure(state="disabled")
        for num, title, text, btn, target in STEPS:
            self._card(num, title, text, btn, target)
        tk.Label(self, text="Mehr", bg=BG, fg=TEXT_DIM, font=FONT_TEXT).pack(anchor="w", padx=16, pady=(12, 0))
        for title, text, btn, target in EXTRAS:
            self._card("•", title, text, btn, target)
        tk.Label(self, text=HINT, bg=BG, fg=TEXT_DIM, font=FONT_TEXT).pack(anchor="w", padx=16, pady=(12, 0))
        # Notizen je Spiel (Spiel-Profil)
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=16, pady=(12, 0))
        tk.Label(head, text="Notizen zu diesem Spiel", bg=BG, fg=TEXT_DIM, font=FONT_TEXT).pack(side="left")
        self.v_prof = tk.StringVar(value="")
        tk.Label(head, textvariable=self.v_prof, bg=BG, fg=TEXT_DIM, font=FONT_TEXT).pack(side="left", padx=12)
        button(head, "LOG-ORDNER ÖFFNEN", self.open_logs).pack(side="right")
        button(head, "AUF UPDATES PRÜFEN", self.check_updates).pack(side="right", padx=8)
        button(head, "NOTIZEN SPEICHERN", self.save_notes).pack(side="right", padx=8)
        self.notes = tk.Text(self, height=5, wrap="word", bg=BG_CARD, fg=TEXT, insertbackground=TEXT, relief="flat", font=FONT_LABEL)
        self.notes.pack(fill="x", padx=16, pady=(4, 8))
        self.notes.bind("<FocusOut>", lambda _e: self.save_notes(quiet=True))
        self._notes_key = object()          # Platzhalter: beim ersten refresh() immer laden
        self.refresh()
        self.after(2000, self._tick)

    def _card(self, num, title, text, btn, target):
        row = tk.Frame(self, bg=BG_CARD)
        row.pack(fill="x", padx=16, pady=4)
        tk.Label(row, text=num, bg=BG_CARD, fg=ACCENT, font=FONT_HEAD, width=3).pack(side="left", padx=4)
        mid = tk.Frame(row, bg=BG_CARD)
        mid.pack(side="left", fill="x", expand=True, pady=8)
        tk.Label(mid, text=title, bg=BG_CARD, fg=TEXT, font=FONT_HEAD, anchor="w").pack(fill="x")
        tk.Label(mid, text=text, bg=BG_CARD, fg=TEXT_DIM, font=FONT_TEXT, anchor="w", justify="left",
                 wraplength=720).pack(fill="x")
        b = button(row, btn, lambda t=target: self.go(t), accent=True)
        b.pack(side="right", padx=12)
        self.buttons[target] = b

    # ------------------------------------------------------------------
    def go(self, target):
        """Knopf: zum passenden Tab / Hauptfenster."""
        if target == "show_main":
            try:
                self.win.app.root.deiconify()
                self.win.app.root.lift()
                self.win.app.root.focus_force()
                entry = getattr(self.win.app, "ip_entry", None)         # IP-Feld: hier fehlt Einsteigern am meisten
                if entry is not None:
                    entry.focus_set()
                    entry.select_range(0, "end")
            except Exception:  # noqa: BLE001
                pass
            return
        if target == "howto":
            self.win.open_howto()
            return
        tab = getattr(self.win, target, None)
        if tab is None:
            self.log("Dieses Werkzeug ist nicht verfügbar", "err")
            return
        self.win.show_tab(tab)

    def run_check(self):
        # Knopf VERBINDUNG PRÜFEN: IP -> PS5 -> Payload -> Spiel, in einem Hintergrund-Job (rein lesend)
        if self._checking:
            return
        app = self.win.app
        try:                                                            # Werte hier (UI-Thread) lesen
            host = app.ip_var.get().strip()
            port = int(app.port_var.get())
        except (AttributeError, ValueError):
            host = getattr(app.backend, "host", "")
            port = getattr(app.backend, "port", conncheck.DEFAULT_PORT)
        proc = getattr(app.backend, "process_name", "eboot.bin")
        lang = tools_i18n.lang()
        self._checking = True
        self._check_steps = None
        self.v_check.set("Prüfe die Verbindung ...")
        tools_ui.paint_message(self.txt_check, "info", tools_i18n.translate("Prüfe die Verbindung ..."))
        self.win.bg(lambda: conncheck.diagnose(host, port, process_name=proc, lang=lang),
                    self._check_done, self._check_failed, lock=False)

    def _check_done(self, steps):
        self._checking = False
        self._check_steps = steps
        self.v_check.set(conncheck.render(steps, tools_i18n.lang()))
        tools_ui.paint_steps(self.txt_check, steps)

    def _check_failed(self, exc):
        self._checking = False
        self.v_check.set(f"{type(exc).__name__}: {exc}")
        tools_ui.paint_message(self.txt_check, "fail", f"{type(exc).__name__}: {exc}")

    def status_items(self):
        # Klartext-Status als Ampel: [(zustand, text)], zustand = ok | fail | info (rein lesend).  Die Texte tragen
        # weiter das Zeichen (✓ / ✗ / •) - so passen die vorhandenen englischen Eintraege, und status_text() bleibt gleich.
        app = self.win.app
        be = app.backend
        if not getattr(be, "client", None) or be.pid is None:
            conn = ("fail", "✗  Nicht verbunden - im Hauptfenster auf VERBINDEN klicken.")
        else:
            conn = ("ok", f"✓  Verbunden mit der PS5 (Spiel-Prozess {be.pid}).")
        proj = getattr(app, "current_project", None)
        n = len(getattr(app, "patches", {}) or {})
        if proj and n:
            codes = ("ok", f"✓  Codes: {n} für „{proj}“ geladen.")
        elif proj:
            codes = ("info", f"•  Projekt „{proj}“ ist offen, enthält aber keine Codes.")
        else:
            codes = ("info", "•  Keine Codes geladen (das Spiel hat keine oder es ist noch nichts gewählt).")
        return [conn, codes]

    def status_text(self):
        # dieselben Zeilen als Text (mit ✓ / ✗ / •)
        return "\n".join(t for _s, t in self.status_items())

    def _paint_status(self):
        for (dot, txt), (state, text) in zip(self._dots, self.status_items()):
            dot.configure(fg=STATE_COLOR.get(state, TEXT_DIM2))
            shown = tools_i18n.translate(text).lstrip("✓✗•! ")      # das Zeichen ersetzt der farbige Punkt
            txt.configure(text=shown)

    def _gp(self):
        return getattr(self.win.app, "gp", None)

    def load_notes(self):
        """Notizen des Spiels anzeigen, wenn sich das Spiel/Projekt geaendert hat."""
        gp = self._gp()
        key = gp.key if gp else None
        if key == self._notes_key:
            return
        self._notes_key = key
        self.notes.delete("1.0", "end")
        if gp:
            self.notes.insert("1.0", gp.notes)
        self.v_prof.set(f"({gp.key})" if gp else "(kein Projekt offen)")

    def save_notes(self, quiet=False):
        gp = self._gp()
        if gp is None:
            if not quiet:
                self.log("Erst ein Projekt/Spiel öffnen - Notizen gehören zum Spiel", "err")
            return
        text = self.notes.get("1.0", "end-1c")
        if text != gp.notes:
            gp.notes = text
            gp.save()
            if not quiet:
                self.log("Notizen gespeichert", "ok")

    def check_updates(self):
        """Manuelle Update-Pruefung (nur lesen; Download-Seite wird erst nach Rueckfrage im Browser geoeffnet)."""
        import update_check
        import version
        url = self.win.app.cfg.get("update_url", "")
        if not url:                                  # Standard: GitHub Releases, mit Installieren-Dialog
            self.win.app.check_for_updates(manual=True)
            return
        self.bg(lambda: update_check.check(url, version.__version__), self._update_result)

    def _update_result(self, res):
        if res.status == "uptodate":
            self.log(f"Du hast die neueste Version ({res.local})", "ok")
        elif res.status == "error":
            self.log(f"Update-Prüfung fehlgeschlagen: {res.error}", "err")
        elif res.status == "newer":
            self.log(f"Neue Version {res.remote} verfügbar (installiert: {res.local})" + (f" - {res.notes}" if res.notes else ""), "ok")
            if res.url and messagebox.askyesno("Update", f"Version {res.remote} ist verfügbar.\n\nDownload-Seite öffnen?"):
                import webbrowser
                webbrowser.open(res.url)

    def open_logs(self):
        import logsetup
        import paths
        d = os.path.dirname(logsetup.current_file() or "") or paths.logs_dir()
        try:
            if os.name == "nt":
                os.startfile(d)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", d])
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception as e:  # noqa: BLE001
            self.log(f"{d}: {e}", "err")

    def refresh(self):
        try:
            self.v_status.set(self.status_text())
            self._paint_status()
            self.load_notes()
        except Exception:  # noqa: BLE001
            pass

    def _tick(self):
        try:
            if not self.winfo_exists():
                return
            self.refresh()
            self.after(2000, self._tick)
        except Exception:  # noqa: BLE001
            pass
