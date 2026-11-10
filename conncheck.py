"""conncheck.py - Verbindungstest in Klartext (ohne tkinter).

    diagnose(host, port)        -> [Step, ...]   IP gueltig? PS5 erreichbar? Payload da? Spiel laeuft?
    summary(steps, lang)        -> ein Satz: was ist das Ergebnis / was als Naechstes tun
    render(steps, lang)         -> Text mit ✓ / ✗ / • je Schritt (fuer eine Anzeige)
    explain_error(exc, ...)     -> Tipp-Satz zu einer Verbindungs-Ausnahme (fuer das Log), oder None

Die Pruefung ist rein lesend: sie oeffnet kurz eine eigene Verbindung, fragt Version und Prozessliste ab und schliesst sie
wieder.  Netzwerk und Client sind austauschbar (tcp_connect / client_factory), damit Tests ohne Konsole laufen.
"""
import errno
import ipaddress
import re
import socket
from dataclasses import dataclass

from ps5_client import COMMON_PORTS, PS5DebugClient

DEFAULT_PORT = 744
BACKCHANNEL_PORT = 755

OK, FAIL, WARN, INFO, SKIP = "ok", "fail", "warn", "info", "skip"
_MARK = {OK: "✓", FAIL: "✗", WARN: "!", INFO: "•", SKIP: "–"}


@dataclass
class Step:
    state: str          # ok | fail | warn | info | skip
    title: str          # kurze Ueberschrift, z. B. "PS5 erreichbar"
    detail: str = ""    # Klartext: was ist los / was tun


def _t(lang, de, en):
    return en if lang == "en" else de


# ---------------------------------------------------------------- Fehlerarten erkennen
_TEXT_KINDS = (
    ("refused", ("10061", "refused", "verweigert", "errno 111")),
    ("timeout", ("timed out", "10060", "zeitüberschreitung", "zeitueberschreitung")),
    ("unreachable", ("10051", "10065", "unreachable", "nicht erreichbar", "no route")),
    ("dns", ("getaddrinfo", "11001", "name or service", "nodename nor servname", "name resolution")),
    ("nogame", ("nicht gefunden", "prozessliste leer")),
    ("protocol", ("version-länge", "version-laenge", "leere version", "kein gültiges ps5debug", "kein gueltiges ps5debug")),
    ("closed", ("verbindung geschlossen", "connection reset", "10054", "broken pipe")),
)
_UNREACHABLE_ERRNO = {errno.ENETUNREACH, errno.EHOSTUNREACH, 10051, 10065}


def classify(exc):
    """Ausnahme -> 'refused' | 'timeout' | 'unreachable' | 'dns' | 'nogame' | 'protocol' | 'closed' | 'other'.
    PS5DebugClient.connect verpackt alles in RuntimeError(... from e): darum die ganze Ursachen-Kette ansehen."""
    chain, seen = [], set()
    e = exc
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        chain.append(e)
        e = e.__cause__ or e.__context__
    for e in chain:                                         # erst nach Typ (genau) ...
        if isinstance(e, ConnectionRefusedError):
            return "refused"
        if isinstance(e, socket.timeout):                   # == TimeoutError ab Python 3.10
            return "timeout"
        if isinstance(e, socket.gaierror):
            return "dns"
        if isinstance(e, OSError) and (e.errno in _UNREACHABLE_ERRNO or getattr(e, "winerror", None) in _UNREACHABLE_ERRNO):
            return "unreachable"
    text = " | ".join(str(e) for e in chain).lower()       # ... dann nach Text (z. B. nach connect_auto)
    for kind, needles in _TEXT_KINDS:
        if any(n in text for n in needles):
            return kind
    return "other"


def hint(kind, host="", port=DEFAULT_PORT, lang="de"):
    """Klartext-Tipp zu einer Fehlerart (ein bis zwei Saetze, sagt was zu tun ist)."""
    if kind == "refused":
        return _t(lang,
                  f"Die PS5 ist da, aber auf Port {port} hört niemand zu: Der Payload (ps5debug-NG) ist nicht geladen. "
                  "Sende ihn mit deinem Payload-Sender erneut - das ist nach jedem Neustart der PS5 nötig.",
                  f"The PS5 answers, but nothing listens on port {port}: the payload (ps5debug-NG) is not loaded. "
                  "Send it again with your payload sender - this is needed after every restart of the PS5.")
    if kind == "timeout":
        return _t(lang,
                  f"Keine Antwort von {host}. Meistens ist die IP falsch oder die PS5 im Ruhemodus/aus. IP nachsehen: "
                  "PS5 Einstellungen -> Netzwerk -> Verbindungsstatus anzeigen. PC und PS5 müssen im selben Netz sein "
                  "(ein VPN oder eine Firewall kann es auch blockieren).",
                  f"No answer from {host}. Usually the IP is wrong or the PS5 is in rest mode/off. Look up the IP: "
                  "PS5 Settings -> Network -> View Connection Status. PC and PS5 must be on the same network "
                  "(a VPN or a firewall can block it, too).")
    if kind == "unreachable":
        return _t(lang,
                  f"Es gibt keinen Weg zu {host}. Sind PC und PS5 im selben Netz (gleiches WLAN / gleicher Router)? "
                  "Stimmen die ersten Zahlen der IP mit denen deines PCs überein?",
                  f"There is no route to {host}. Are the PC and the PS5 on the same network (same Wi-Fi / router)? "
                  "Do the first numbers of the IP match those of your PC?")
    if kind == "dns":
        return _t(lang,
                  f"Der Name „{host}“ ist unbekannt. Trage die IP-Adresse der PS5 ein, zum Beispiel 192.168.1.20.",
                  f"The name “{host}” is unknown. Enter the IP address of the PS5, for example 192.168.1.20.")
    if kind == "protocol":
        return _t(lang,
                  f"Auf {host}:{port} antwortet etwas, aber nicht ps5debug-NG. Läuft dort ein anderer Payload? "
                  "Lade ps5debug-NG und versuche es noch einmal.",
                  f"Something answers on {host}:{port}, but it is not ps5debug-NG. Is another payload running there? "
                  "Load ps5debug-NG and try again.")
    if kind == "closed":
        return _t(lang,
                  "Die PS5 hat die Verbindung sofort wieder getrennt. Meist ist der Payload hängengeblieben: "
                  "PS5 neu starten, Payload neu laden, Spiel starten und es noch einmal versuchen.",
                  "The PS5 closed the connection right away. Usually the payload got stuck: restart the PS5, "
                  "load the payload again, start the game and try again.")
    if kind == "nogame":
        return _t(lang,
                  "Der Payload läuft, aber ich finde kein Spiel. Starte das Spiel, lade deinen Spielstand "
                  "und prüfe dann noch einmal.",
                  "The payload is running, but I cannot find a game. Start the game, load your save "
                  "and check again.")
    return ""


def explain_error(exc, host="", port=DEFAULT_PORT, lang="de"):
    """Tipp-Satz fuer das Log, wenn VERBINDEN scheitert - oder None, wenn wir nichts Sinnvolles sagen koennen."""
    h = hint(classify(exc), host, port, lang)
    return h or None


# ---------------------------------------------------------------- Eingabe pruefen
_DOTTED = re.compile(r"^[0-9.]+$")


def check_host(host, lang="de"):
    """(ok, Klartext).  Gueltige IPv4/IPv6 oder ein Rechnername; typische Eingabefehler werden benannt."""
    h = (host or "").strip()
    if not h:
        return False, _t(lang, "Es ist keine IP-Adresse eingetragen. Trage oben im Hauptfenster die IP deiner PS5 ein.",
                         "No IP address is entered. Enter the IP of your PS5 at the top of the main window.")
    if "://" in h or "/" in h or " " in h:
        return False, _t(lang, "Die Adresse sieht nicht nach einer IP aus. Trage nur die Zahlen ein, zum Beispiel 192.168.1.20.",
                         "That does not look like an IP address. Enter only the numbers, for example 192.168.1.20.")
    if h.count(":") == 1:
        return False, _t(lang, "Hier steht ein Doppelpunkt: Trage nur die IP ein. Der Port kommt in das kleine Feld daneben.",
                         "There is a colon: enter only the IP. The port goes into the small field next to it.")
    if _DOTTED.match(h):
        try:
            ipaddress.IPv4Address(h)
        except ValueError:
            return False, _t(lang, f"„{h}“ ist keine gültige IP-Adresse (vier Zahlen von 0 bis 255, mit Punkten getrennt).",
                             f"“{h}” is not a valid IP address (four numbers from 0 to 255, separated by dots).")
        if h in ("0.0.0.0", "255.255.255.255"):
            return False, _t(lang, f"{h} kann keine PS5 sein. Schau die IP in den Netzwerk-Einstellungen der PS5 nach.",
                             f"{h} cannot be a PS5. Look up the IP in the network settings of the PS5.")
    return True, _t(lang, f"Adresse {h} sieht gut aus.", f"Address {h} looks fine.")


# ---------------------------------------------------------------- Netzwerk (austauschbar)
def _tcp_connect(host, port, timeout):
    s = socket.create_connection((host, port), timeout=timeout)
    s.close()


def _client_factory(host, port, timeout):
    return PS5DebugClient(host, port, timeout=timeout)


def diagnose(host, port=DEFAULT_PORT, process_name="eboot.bin", lang="de", timeout=3.0,
             tcp_connect=None, client_factory=None):
    """Prueft der Reihe nach; nach dem ersten Fehler werden die folgenden Schritte als 'skip' gezeigt."""
    tcp = tcp_connect or _tcp_connect
    make = client_factory or _client_factory
    host = (host or "").strip()
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = DEFAULT_PORT
    titles = (_t(lang, "Adresse", "Address"), _t(lang, "PS5 erreichbar", "PS5 reachable"),
              _t(lang, "Payload antwortet", "Payload answers"), _t(lang, "Spiel läuft", "Game is running"))
    steps = []
    put = steps.append                                      # (Texte sind schon zweisprachig - kein Eintrag in tools_i18n_en noetig)

    def fail_rest(i):
        steps.extend(Step(SKIP, titles[k]) for k in range(i, len(titles)))

    # 1 Adresse
    ok, text = check_host(host, lang)
    put(Step(OK if ok else FAIL, titles[0], text))
    if not ok:
        fail_rest(1)
        return steps

    # 2 PS5 erreichbar (TCP)
    try:
        tcp(host, port, timeout)
        put(Step(OK, titles[1], _t(lang, f"Die PS5 antwortet auf Port {port}.", f"The PS5 answers on port {port}.")))
    except Exception as e:  # noqa: BLE001 - jede Art von Netzfehler wird erklaert
        kind = classify(e)
        alt = None
        if kind == "refused":                               # PS5 lebt: vielleicht lauscht der Payload auf einem anderen Port
            for p in COMMON_PORTS:
                if p == port:
                    continue
                try:
                    tcp(host, p, 0.7)
                    alt = p
                    break
                except Exception:  # noqa: BLE001
                    continue
        if alt is not None:
            port = alt
            put(Step(WARN, titles[1], _t(lang,
                              f"Auf dem eingetragenen Port hört niemand, aber auf Port {alt} antwortet die PS5. "
                              f"Ich benutze {alt} - trage ihn im Hauptfenster in das Port-Feld ein.",
                              f"Nothing listens on the entered port, but the PS5 answers on port {alt}. "
                              f"I use {alt} - enter it in the port field of the main window.")))
        else:
            put(Step(FAIL, titles[1], hint(kind, host, port, lang) or
                              _t(lang, f"Verbindung nicht möglich ({e}).", f"Cannot connect ({e}).")))
            fail_rest(2)
            return steps

    # 3 Payload spricht ps5debug-NG
    client = None
    try:
        client = make(host, port, timeout)
        version = client.connect()
        put(Step(OK, titles[2], _t(lang, f"ps5debug-NG antwortet (Protokoll {version}).",
                                            f"ps5debug-NG answers (protocol {version}).")))
    except Exception as e:  # noqa: BLE001
        kind = {"other": "protocol", "timeout": "closed"}.get(classify(e), classify(e))   # TCP stand schon: haengender Payload
        put(Step(FAIL, titles[2], hint(kind, host, port, lang) or
                          _t(lang, f"Keine Antwort vom Payload ({e}).", f"No answer from the payload ({e}).")))
        _close(client)
        fail_rest(3)
        return steps

    # 4 Spiel laeuft
    try:
        pid = client.find_pid(process_name)
        put(Step(OK, titles[3], _t(lang, f"Spiel gefunden (Prozess {pid}).", f"Game found (process {pid}).")))
    except Exception as e:  # noqa: BLE001
        kind = classify(e)
        put(Step(FAIL, titles[3], hint("nogame" if kind in ("nogame", "other") else kind, host, port, lang)))
    finally:
        _close(client)

    if all(s.state in (OK, WARN) for s in steps):
        put(Step(INFO, _t(lang, "Hinweis", "Note"), _t(lang,
                          f"Alles bereit - klicke im Hauptfenster auf VERBINDEN. Für Beobachten und Debugger muss deine Firewall "
                          f"Port {BACKCHANNEL_PORT} erlauben (die PS5 meldet sich dort zurück).",
                          f"All set - click CONNECT in the main window. For watching and the debugger your firewall must allow "
                          f"port {BACKCHANNEL_PORT} (the PS5 reports back there).")))
    return steps


def _close(client):
    if client is not None:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------- Anzeige
def summary(steps, lang="de"):
    """Ein Satz: Ergebnis der Pruefung."""
    for s in steps:
        if s.state == FAIL:
            return f"{s.title}: {s.detail}" if s.detail else s.title
    return _t(lang, "Alles in Ordnung - du kannst im Hauptfenster auf VERBINDEN klicken.",
              "Everything is fine - you can click CONNECT in the main window.")


def render(steps, lang="de"):
    """Mehrzeiliger Text: je Schritt eine Zeile, bei Fehlern/Hinweisen mit dem Klartext darunter."""
    lines = []
    for s in steps:
        lines.append(f"{_MARK.get(s.state, '•')}  {s.title}")
        if s.detail and s.state in (FAIL, WARN, INFO):
            lines.append(f"     {s.detail}")
    return "\n".join(lines)
