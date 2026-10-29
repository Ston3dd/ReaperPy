"""tools_start_gui.py - Tab "START": Einstieg fuer Anfaenger (drei Schritte, grosse Knoepfe, Klartext).

Zeigt, ob die PS5 verbunden ist und welches Spiel/welche Codes gerade offen sind, und fuehrt per Knopfdruck zu den
einfachen Werkzeugen.  Alles Spezielle liegt im Tab FORTGESCHRITTEN.
"""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

from tools_common import ACCENT, BG, BG_CARD, FONT_HEAD, FONT_LABEL, TEXT, TEXT_DIM, BaseTab, button

STEPS = [
    ("1", "Spiel verbinden",
     "Starte dein Spiel und lade den Spielstand. Klicke im Hauptfenster oben auf VERBINDEN. "
     "Wenn das Spiel Codes hat, erscheinen sie dort automatisch.",
     "HAUPTFENSTER ZEIGEN", "show_main"),
    ("2", "Wert suchen",
     "Du siehst im Spiel eine Zahl (z. B. 100 Leben oder 5000 Gold)? Suche sie, ändere sie im Spiel, "
     "suche nochmal - bis nur noch wenige Treffer übrig sind. Dann kannst du den Wert ändern.",
     "ZU WERT SUCHEN", "scan_tab"),
    ("3", "Als Cheat speichern",
     "Gefundene Adressen kommen in die Cheat-Liste. Dort gibst du ihnen einen Namen und exportierst sie "
     "für dein Cheat-Menü.",
     "ZU CHEATS BEARBEITEN", "t_cheat"),
]
EXTRAS = [
    ("Unreal-Engine-Spiel: Items als Trainer", "Alle Items eines Unreal-Spiels automatisch finden und als fertigen "
     "Trainer speichern - in drei Klicks.", "ZU ITEMS", "items_tab"),
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
        self.buttons = {}
        tk.Label(self, text="▸  WILLKOMMEN BEI REAPERPY", bg=BG, fg=ACCENT, font=FONT_HEAD).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(self, text="In drei Schritten zum eigenen Cheat - ohne Vorkenntnisse.", bg=BG, fg=TEXT_DIM,
                 font=FONT_LABEL).pack(anchor="w", padx=16)
        box = tk.Frame(self, bg=BG_CARD)
        box.pack(fill="x", padx=16, pady=10)
        tk.Label(box, textvariable=self.v_status, bg=BG_CARD, fg=TEXT, font=FONT_LABEL, justify="left",
                 anchor="w").pack(fill="x", padx=12, pady=8)
        for num, title, text, btn, target in STEPS:
            self._card(num, title, text, btn, target)
        tk.Label(self, text="Mehr", bg=BG, fg=TEXT_DIM, font=FONT_LABEL).pack(anchor="w", padx=16, pady=(10, 0))
        for title, text, btn, target in EXTRAS:
            self._card("•", title, text, btn, target)
        tk.Label(self, text=HINT, bg=BG, fg=TEXT_DIM, font=FONT_LABEL).pack(anchor="w", padx=16, pady=(12, 0))
        # Notizen je Spiel (Spiel-Profil)
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=16, pady=(12, 0))
        tk.Label(head, text="Notizen zu diesem Spiel", bg=BG, fg=TEXT_DIM, font=FONT_LABEL).pack(side="left")
        self.v_prof = tk.StringVar(value="")
        tk.Label(head, textvariable=self.v_prof, bg=BG, fg=TEXT_DIM, font=FONT_LABEL).pack(side="left", padx=10)
        button(head, "LOG-ORDNER ÖFFNEN", self.open_logs).pack(side="right")
        button(head, "AUF UPDATES PRÜFEN", self.check_updates).pack(side="right", padx=6)
        button(head, "NOTIZEN SPEICHERN", self.save_notes).pack(side="right", padx=6)
        self.notes = tk.Text(self, height=5, wrap="word", bg=BG_CARD, fg=TEXT, insertbackground=TEXT, relief="flat", font=FONT_LABEL)
        self.notes.pack(fill="x", padx=16, pady=(4, 8))
        self.notes.bind("<FocusOut>", lambda _e: self.save_notes(quiet=True))
        self._notes_key = object()          # Platzhalter: beim ersten refresh() immer laden
        self.refresh()
        self.after(2000, self._tick)

    def _card(self, num, title, text, btn, target):
        row = tk.Frame(self, bg=BG_CARD)
        row.pack(fill="x", padx=16, pady=3)
        tk.Label(row, text=num, bg=BG_CARD, fg=ACCENT, font=FONT_HEAD, width=3).pack(side="left", padx=4)
        mid = tk.Frame(row, bg=BG_CARD)
        mid.pack(side="left", fill="x", expand=True, pady=6)
        tk.Label(mid, text=title, bg=BG_CARD, fg=TEXT, font=FONT_HEAD, anchor="w").pack(fill="x")
        tk.Label(mid, text=text, bg=BG_CARD, fg=TEXT_DIM, font=FONT_LABEL, anchor="w", justify="left",
                 wraplength=720).pack(fill="x")
        b = button(row, btn, lambda t=target: self.go(t), accent=True)
        b.pack(side="right", padx=10)
        self.buttons[target] = b

    # ------------------------------------------------------------------
    def go(self, target):
        """Knopf: zum passenden Tab / Hauptfenster."""
        if target == "show_main":
            try:
                self.win.app.root.deiconify()
                self.win.app.root.lift()
                self.win.app.root.focus_force()
            except Exception:  # noqa: BLE001
                pass
            return
        tab = getattr(self.win, target, None)
        if tab is None:
            self.log("Dieses Werkzeug ist nicht verfügbar", "err")
            return
        self.win.show_tab(tab)

    def status_text(self):
        """Klartext-Status (rein lesend)."""
        app = self.win.app
        be = app.backend
        if not getattr(be, "client", None) or be.pid is None:
            conn = "✗  Nicht verbunden - im Hauptfenster auf VERBINDEN klicken."
        else:
            conn = f"✓  Verbunden mit der PS5 (Spiel-Prozess {be.pid})."
        proj = getattr(app, "current_project", None)
        n = len(getattr(app, "patches", {}) or {})
        if proj and n:
            codes = f"✓  Codes: {n} für „{proj}“ geladen."
        elif proj:
            codes = f"•  Projekt „{proj}“ ist offen, enthält aber keine Codes."
        else:
            codes = "•  Keine Codes geladen (das Spiel hat keine oder es ist noch nichts gewählt)."
        return conn + "\n" + codes

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
