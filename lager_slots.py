
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import traceback

from ps5_backend import PS5Backend


# ==================================================
# EINSTELLUNGEN
# ==================================================

DEFAULT_IP = "192.168.137.2"
DEFAULT_PORT = 744

STRIDE = 0x18
EN_OFF = 0x0C

DEFAULT_SLOTS = 60
TOTAL_SLOTS = 500

# Die bekannte Referenzadresse:
DEFAULT_ADDRESS = "0x10050011F8"


# ==================================================
# SPEICHERZUGRIFF
# ==================================================

class Memory:

    def __init__(self, backend):
        self.backend = backend

    def read(self, address, size):
        data = self.backend.client.read_memory(
            address, size
        )

        if data is None:
            raise RuntimeError(
                f"Lesefehler bei 0x{address:X}"
            )

        data = bytes(data)

        if len(data) != size:
            raise RuntimeError(
                f"Unvollständiger Lesezugriff bei "
                f"0x{address:X}: {len(data)} statt {size} Bytes"
            )

        return data

    def write(self, address, data):
        return self.backend.client.write_memory(
            address, bytes(data)
        )

    def entry(self, address):
        return self.read(address, STRIDE)


# ==================================================
# EINTRAGSPRÜFUNG
# ==================================================

def plausible(entry):

    if len(entry) != STRIDE:
        return False

    count = int.from_bytes(
        entry[0:4],
        "little",
        signed=True
    )

    enabled = entry[EN_OFF]
    register = entry[0x0E]

    if count < 0 or count > 1_000_000:
        return False

    if enabled not in (0, 1):
        return False

    if register not in (0, 1):
        return False

    return True


# ==================================================
# LISTENANFANG FINDEN
# ==================================================

def find_run(mem, item_address, slots):

    candidates = []
    read_errors = []

    for back in range(slots):

        start = item_address - back * STRIDE
        valid = True

        for index in range(slots):

            address = start + index * STRIDE

            try:
                entry = mem.entry(address)

            except Exception as exc:
                read_errors.append(
                    f"0x{address:X}: {exc}"
                )
                valid = False
                break

            if not plausible(entry):
                valid = False
                break

            if entry[EN_OFF] != 1:
                valid = False
                break

        if not valid:
            continue

        try:
            next_entry = mem.entry(
                start + slots * STRIDE
            )

        except Exception as exc:
            read_errors.append(str(exc))
            continue

        if not plausible(next_entry):
            continue

        if next_entry[EN_OFF] != 0:
            continue

        candidates.append(start)

    candidates = list(dict.fromkeys(candidates))

    if not candidates:

        if read_errors:
            raise RuntimeError(
                "Keine passende Liste gefunden.\n\n"
                "Speicherfehler:\n"
                + "\n".join(read_errors[:5])
            )

        raise RuntimeError(
            "Keine passende Liste gefunden.\n"
            "Erwartet wurden 60 aktivierte Einträge "
            "und ein deaktivierter Folgeeintrag."
        )

    if len(candidates) > 1:

        addresses = "\n".join(
            f"0x{x:X}" for x in candidates[:10]
        )

        raise RuntimeError(
            "Mehrere mögliche Listenanfänge gefunden:\n"
            + addresses
        )

    return candidates[0]


# ==================================================
# SLOTS 1 BIS 500 PRÜFEN
# ==================================================

def validate_list(mem, start):

    targets = []

    check_slots = [
        1, 60, 61, 100, 200,
        250, 251, 300, 400, 499, 500
    ]

    for slot in range(1, TOTAL_SLOTS + 1):

        address = start + (slot - 1) * STRIDE
        entry = mem.entry(address)

        if not plausible(entry):
            raise RuntimeError(
                f"Ungültiger Eintrag bei Slot {slot}\n"
                f"Adresse: 0x{address:X}\n"
                "Es wurde nichts geschrieben."
            )

        if slot in check_slots:
            print_info = (
                f"Slot {slot}: "
                f"Adresse 0x{address:X}, "
                f"Enable={entry[EN_OFF]:02X}, "
                f"Typ={entry[EN_OFF + 1]:02X}"
            )
            yield_log.append(print_info)

        if slot > DEFAULT_SLOTS:
            targets.append(address + EN_OFF)

    return targets


# ==================================================
# FREISCHALTEN
# ==================================================

def enable_all(mem, targets, log):

    written = 0

    for address in targets:

        mem.write(address, b"\x01")

        check = mem.read(address, 1)

        if check != b"\x01":
            raise RuntimeError(
                f"Rückleseprüfung fehlgeschlagen:\n"
                f"0x{address:X}\n"
                f"Bis dahin geschrieben: {written}"
            )

        written += 1

        if written % 25 == 0:
            log(f"{written} Slots geschrieben ...")

    return written


# ==================================================
# GUI
# ==================================================

class LagerGUI:

    def __init__(self, root):

        self.root = root
        self.root.title("Lager Slots – PPSA06929")
        self.root.geometry("650x560")
        self.root.resizable(False, False)

        self.backend = None
        self.mem = None
        self.pid = None

        self.start_address = None
        self.targets = None
        self.checked = False
        self.busy = False

        self.build_ui()

    def build_ui(self):

        frame = ttk.Frame(self.root, padding=15)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Lager Slots – PPSA06929",
            font=("Segoe UI", 16, "bold")
        ).pack(anchor="w", pady=(0, 15))

        ttk.Label(frame, text="PS5-IP-Adresse").pack(anchor="w")

        self.ip_entry = ttk.Entry(frame)
        self.ip_entry.insert(0, DEFAULT_IP)
        self.ip_entry.pack(fill="x", pady=(2, 10))

        ttk.Label(frame, text="Port").pack(anchor="w")

        self.port_entry = ttk.Entry(frame)
        self.port_entry.insert(0, str(DEFAULT_PORT))
        self.port_entry.pack(fill="x", pady=(2, 10))

        ttk.Label(
            frame,
            text="Stückzahl-Adresse (+0x00 des Eintrags)"
        ).pack(anchor="w")

        self.address_entry = ttk.Entry(frame)
        self.address_entry.insert(0, DEFAULT_ADDRESS)
        self.address_entry.pack(fill="x", pady=(2, 10))

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=5)

        ttk.Label(
            row,
            text="Bereits freigeschaltet:"
        ).pack(side="left")

        self.slots_entry = ttk.Entry(row, width=8)
        self.slots_entry.insert(0, str(DEFAULT_SLOTS))
        self.slots_entry.pack(side="left", padx=8)

        ttk.Label(
            row,
            text="Gesamtzahl: 500"
        ).pack(side="left", padx=(15, 0))

        ttk.Separator(frame).pack(fill="x", pady=12)

        # Button 1: Nur prüfen
        self.check_button = ttk.Button(
            frame,
            text="1. PRÜFEN – KEINE SCHREIBZUGRIFFE",
            command=self.start_check
        )
        self.check_button.pack(fill="x", pady=5)

        # Button 2: Freischalten
        self.enable_button = ttk.Button(
            frame,
            text="2. SLOTS 61–500 FREISCHALTEN",
            command=self.start_enable,
            state="disabled"
        )
        self.enable_button.pack(fill="x", pady=5)

        self.status = ttk.Label(
            frame,
            text="Nicht verbunden.",
            foreground="blue"
        )
        self.status.pack(anchor="w", pady=(12, 5))

        self.output = tk.Text(
            frame,
            height=15,
            wrap="word",
            font=("Consolas", 9)
        )
        self.output.pack(fill="both", expand=True)

    # ==================================================
    # GUI-HILFSFUNKTIONEN
    # ==================================================

    def log(self, text):
        self.root.after(
            0, self._append_log, str(text)
        )

    def _append_log(self, text):
        self.output.insert("end", text + "\n")
        self.output.see("end")

    def set_status(self, text):
        self.root.after(
            0,
            lambda: self.status.config(text=text)
        )

    def set_buttons(self, checking=False, ready=False):

        def update():
            self.check_button.config(
                state="disabled" if checking else "normal"
            )

            self.enable_button.config(
                state="normal" if ready else "disabled"
            )

        self.root.after(0, update)

    # ==================================================
    # EINGABEN
    # ==================================================

    def get_values(self):

        ip = self.ip_entry.get().strip()
        port = int(self.port_entry.get().strip())

        address = int(
            self.address_entry.get().strip(),
            16
        )

        slots = int(self.slots_entry.get().strip())

        if not ip:
            raise ValueError("IP-Adresse fehlt.")

        if not 1 <= port <= 65535:
            raise ValueError("Ungültiger Port.")

        if not 1 <= slots < TOTAL_SLOTS:
            raise ValueError(
                "Bereits freigeschaltete Slots müssen "
                "zwischen 1 und 499 liegen."
            )

        return ip, port, address, slots

    # ==================================================
    # VERBINDUNG
    # ==================================================

    def connect_backend(self):

        ip, port, _, _ = self.get_values()

        self.log(f"Verbinde mit {ip}:{port} ...")

        backend = PS5Backend(ip, port)
        backend.connect()

        pid = backend.find_pid()

        if not pid:
            raise RuntimeError(
                "Spielprozess wurde nicht gefunden."
            )

        self.backend = backend
        self.pid = pid
        self.mem = Memory(backend)

        self.log(f"Verbindung hergestellt. PID: {pid}")

    # ==================================================
    # PRÜFEN
    # ==================================================

    def start_check(self):

        if self.busy:
            return

        self.busy = True
        self.checked = False
        self.targets = None
        self.start_address = None

        self.set_buttons(checking=True, ready=False)
        self.set_status("Prüfe Speicher ...")

        threading.Thread(
            target=self.check_worker,
            daemon=True
        ).start()

    def check_worker(self):

        global yield_log
        yield_log = []

        try:

            _, _, address, slots = self.get_values()

            self.connect_backend()

            self.log(f"Referenzadresse: 0x{address:X}")

            test = self.mem.read(address, STRIDE)

            self.log("Direkter Speicher-Lesetest erfolgreich.")
            self.log("Bytes: " + test.hex(" ").upper())

            self.log(
                f"Suche {slots} aktivierte Einträge ..."
            )

            start = find_run(
                self.mem,
                address,
                slots
            )

            self.log(
                f"Listenanfang gefunden: 0x{start:X}"
            )

            self.log(
                f"Prüfe alle {TOTAL_SLOTS} Einträge ..."
            )

            targets = []

            for slot in range(1, TOTAL_SLOTS + 1):

                entry_address = (
                    start + (slot - 1) * STRIDE
                )

                entry = self.mem.entry(entry_address)

                if not plausible(entry):
                    raise RuntimeError(
                        f"Ungültiger Eintrag bei Slot {slot}\n"
                        f"Adresse: 0x{entry_address:X}\n"
                        "Es wurde nichts geschrieben."
                    )

                if slot in (
                    1, 60, 61, 100, 200,
                    250, 251, 300, 400, 499, 500
                ):
                    self.log(
                        f"Slot {slot}: "
                        f"0x{entry_address:X}, "
                        f"Enable={entry[EN_OFF]:02X}, "
                        f"Typ={entry[EN_OFF + 1]:02X}"
                    )

                if slot > slots:
                    targets.append(
                        entry_address + EN_OFF
                    )

            # Letzten Slot nochmals gezielt anzeigen
            last_address = (
                start + (TOTAL_SLOTS - 1) * STRIDE
            )

            self.log(
                f"Letzter Eintrag (Slot 500): "
                f"0x{last_address:X}"
            )

            self.log(
                f"Slot 500 Freischalt-Byte: "
                f"0x{last_address + EN_OFF:X}"
            )

            self.start_address = start
            self.targets = targets
            self.checked = True

            self.log(
                f"PRÜFUNG ERFOLGREICH: "
                f"{TOTAL_SLOTS} Einträge gelesen."
            )

            self.log(
                f"{len(targets)} Slots für den "
                "Freischaltvorgang vorbereitet."
            )

            self.set_status("Prüfung erfolgreich.")

            self.root.after(
                0,
                lambda: self.set_buttons(
                    checking=False,
                    ready=True
                )
            )

        except Exception as exc:

            self.log("FEHLER: " + str(exc))
            self.log(traceback.format_exc())

            self.checked = False
            self.set_status("Prüfung fehlgeschlagen.")
            self.set_buttons()

        finally:
            self.busy = False

    # ==================================================
    # FREISCHALTEN
    # ==================================================

    def start_enable(self):

        if self.busy:
            return

        if not self.checked or self.targets is None:
            messagebox.showwarning(
                "Nicht geprüft",
                "Bitte zuerst den Prüflauf durchführen."
            )
            return

        count = len(self.targets)

        confirmed = messagebox.askyesno(
            "Freischalten bestätigen",
            f"Listenanfang: 0x{self.start_address:X}\n\n"
            f"Bereits aktiv: {self.slots_entry.get()}\n"
            f"Gesamtzahl: {TOTAL_SLOTS}\n"
            f"Zu ändernde Einträge: {count}\n\n"
            "Es werden ausschließlich die bEnable-Bytes "
            "der geprüften Einträge 61–500 geändert.\n\n"
            "Fortfahren?"
        )

        if not confirmed:
            return

        self.busy = True
        self.set_buttons(checking=True, ready=False)
        self.set_status("Freischaltung läuft ...")

        threading.Thread(
            target=self.enable_worker,
            daemon=True
        ).start()

    def enable_worker(self):

        try:

            self.log("Freischaltung gestartet ...")

            written = enable_all(
                self.mem,
                self.targets,
                self.log
            )

            self.log(
                f"FERTIG: {written} Bytes geschrieben "
                "und einzeln zurückgelesen."
            )

            self.set_status("Freischaltung abgeschlossen.")

        except Exception as exc:

            self.log("FEHLER: " + str(exc))
            self.log(traceback.format_exc())

            self.set_status("Fehler beim Schreiben.")

        finally:
            self.busy = False
            self.set_buttons(ready=self.checked)


# ==================================================
# START
# ==================================================

if __name__ == "__main__":

    root = tk.Tk()
    app = LagerGUI(root)
    root.mainloop()
