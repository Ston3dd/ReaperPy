"""cheatmenu.py - Cheat-Menue aus dem SDK, OHNE CheatManager (der fehlt in Shipping-Builds).

Jeder Eintrag schreibt nur gewoehnliche Speicherwerte der Spielfigur - kein Funktionsaufruf, kein Code-Patch:

  Weg 1  Engine-Werte, die jedes UE-Spiel hat (bCanBeDamaged, CharacterMovement.MovementMode/MaxWalkSpeed ...)
  Weg 2  spielspezifische Werte aus dem SDK (Leben, Ausdauer, Geld ...; Kandidaten aus uecheat.py)

Die Werte werden - wie im Tab UE-LIVE - mit dem Freezer festgehalten.  Alles haengt an der Figur, die der
PlayerController gerade steuert; wechselt sie (Tod, Ladebildschirm, neues Level), werden die Adressen verworfen,
statt in freigegebenen Speicher zu schreiben.

Ohne Oberflaeche und ohne Konsole testbar: live/sdk/client werden hereingereicht.
"""
import struct
from dataclasses import dataclass, field

import ue_quick as Q

MAX_PTR = 0x0000_8000_0000_0000
OUTER_DEPTH = 6          # so weit wird die Outer-Kette einer Instanz nach der Spielfigur abgesucht
AUTO = ("", "auto", "max")


class MenuError(ValueError):
    pass


@dataclass
class Entry:
    key: str
    cat: str
    label: str
    kind: str                       # "toggle" | "value"
    cls: str                        # Klasse des Members (SDK-Name)
    member: str
    type: str = ""
    bit: int = -1
    offset: int = -1                # SDK-Offset (Fallback; live wird der Offset aus dem Spiel gelesen)
    source: str = "engine"          # "engine" | "spiel"
    root: str = "pawn"              # pawn | controller | state | world
    steps: tuple = ()               # ((Klasse, Member), ...) Zeiger-Kette ab root
    on: object = None
    off: object = None
    default: str = "auto"
    note: str = ""
    also: tuple = ()                # Schluessel versteckter Eintraege, die mit umgeschaltet werden
    hidden: bool = False
    status: str = ""                # "" = bereit, sonst der Grund (in einfachen Worten), warum es nicht geht
    active: bool = False
    held: bool = False
    addrs: list = field(default_factory=list)   # aktuell beschriebene/festgehaltene Adressen
    companions: list = field(default_factory=list)   # [(Member, Typ, Offset)] Max-Werte fuer 'auto'
    target: object = None           # Q.Target (bei Wrapper-Structs mit parent/sub)

    @property
    def ok(self):
        return not self.status


# Weg 1: Engine-Werte.  (MovementMode: TEnumAsByte -> als uint8; EMovementMode: 1 = Walking, 3 = Falling, 5 = Flying)
ENGINE = [
    dict(key="god", cat="Überleben", label="Unverwundbar (bCanBeDamaged aus)", kind="toggle",
         cls="AActor", member="bCanBeDamaged", on=False, off=True,
         note="Wirkt nur, wenn das Spiel den Standard-Schaden der Engine benutzt. Eigene HP-Systeme ignorieren es - "
              "dann unten 'Leben' nehmen."),
    dict(key="cheatfly", cat="Bewegung", label="bCheatFlying", kind="toggle", hidden=True,
         cls="UCharacterMovementComponent", member="bCheatFlying", on=True, off=False,
         steps=(("ACharacter", "CharacterMovement"),)),
    dict(key="fly", cat="Bewegung", label="Fliegen (MovementMode = Flying)", kind="toggle",
         cls="UCharacterMovementComponent", member="MovementMode", type="uint8", on=5, off=3,
         steps=(("ACharacter", "CharacterMovement"),), also=("cheatfly",),
         note="Mit AN/AUS ein- und ausschalten; beim Ausschalten faellt die Figur wieder."),
    dict(key="walkspeed", cat="Bewegung", label="Lauftempo (MaxWalkSpeed)", kind="value", default="1200",
         cls="UCharacterMovementComponent", member="MaxWalkSpeed", steps=(("ACharacter", "CharacterMovement"),)),
    dict(key="flyspeed", cat="Bewegung", label="Flugtempo (MaxFlySpeed)", kind="value", default="3000",
         cls="UCharacterMovementComponent", member="MaxFlySpeed", steps=(("ACharacter", "CharacterMovement"),)),
    dict(key="jump", cat="Bewegung", label="Sprunghoehe (JumpZVelocity)", kind="value", default="1400",
         cls="UCharacterMovementComponent", member="JumpZVelocity", steps=(("ACharacter", "CharacterMovement"),)),
    dict(key="gravity", cat="Bewegung", label="Schwerkraft (GravityScale)", kind="value", default="0.3",
         cls="UCharacterMovementComponent", member="GravityScale", steps=(("ACharacter", "CharacterMovement"),)),
    dict(key="ptime", cat="Zeit", label="Nur die Figur schneller/langsamer (CustomTimeDilation)", kind="value",
         default="1.5", cls="AActor", member="CustomTimeDilation"),
    dict(key="wtime", cat="Zeit", label="Ganzes Spiel schneller/langsamer (TimeDilation)", kind="value",
         default="0.5", cls="AWorldSettings", member="TimeDilation", root="world"),
]

# Kategorien aus uecheat.py, die als Weg 2 ins Menue kommen: (Kategorie, Anzeigename, Art)
GAME_CATS = [("Cheat-Schalter", "Schalter", "toggle"), ("Leben", "Leben", "value"), ("Ausdauer", "Ausdauer", "value"),
             ("Mana/Energie", "Mana/Energie", "value"), ("Schild/Rüstung", "Schild/Rüstung", "value"),
             ("Munition", "Munition", "value"), ("Währung", "Geld", "value"),
             ("Erfahrung", "Erfahrung/Level", "value")]
PER_CAT = 3


def _valid(p):
    return 0x10000 <= p < MAX_PTR


class CheatMenu:
    def __init__(self, live, sdk, client, log=print):
        self.live, self.sdk, self.client, self.log = live, sdk, client, log
        self.freezer = Q.Freezer()
        self.entries = []
        self.by_key = {}
        self._sig = None            # {"controller", "pawn", "state"} der Figur, an der die Adressen haengen
        self._orig = {}             # vaddr -> (Target, Originalwert)
        self._world = 0

    # ------------------------------------------------------------------ Speicher / SDK
    def _read(self, addr, n):
        return self.client.read_memory(addr, n)

    def _ptr(self, addr):
        p = struct.unpack("<Q", self._read(addr, 8))[0]
        return p if _valid(p) else 0

    def _off(self, cls, member):
        """Offset live aus dem Spiel (die Header koennen zu einer anderen Version gehoeren), sonst aus dem SDK."""
        try:
            o = self.live.member_offset(cls, member)
        except Exception:  # noqa: BLE001
            o = None
        if o is not None:
            return o
        m = self.sdk.find_member(cls, member) if self.sdk is not None else None
        return m.offset if m is not None else None

    def _instances(self, cls):
        return [i for i in self.live.instances(cls) if "Default__" not in i["name"]]

    # ------------------------------------------------------------------ Spielfigur
    def roots(self, fresh=False):
        """{'controller','pawn','state','world'} der gerade gesteuerten Figur.  Der PlayerController wird gemerkt
        (Objektliste durchsuchen ist langsam); fresh=True sucht neu."""
        ctrl = 0 if fresh else (self._sig or {}).get("controller", 0)
        o_pawn = self._off("AController", "Pawn")
        if o_pawn is None:
            o_pawn = self._off("APlayerController", "AcknowledgedPawn")
        if o_pawn is None:
            raise MenuError("AController.Pawn wurde im SDK/Spiel nicht gefunden - die Spielfigur ist nicht erreichbar")
        o_state = self._off("AController", "PlayerState")
        cands = [ctrl] if ctrl else [i["addr"] for i in self._instances("APlayerController")]
        if not cands:
            raise MenuError("Kein PlayerController im Spiel - Spielstand laden (nicht im Hauptmenue)")
        for c in cands:
            pawn = self._ptr(c + o_pawn)
            if pawn:
                return {"controller": c, "pawn": pawn, "state": self._ptr(c + o_state) if o_state is not None else 0,
                        "world": self._world_settings(fresh)}
        raise MenuError("Der PlayerController steuert gerade keine Figur (Hauptmenue oder Ladebildschirm?)")

    def _world_settings(self, fresh):
        if fresh or not self._world:
            ws = self._instances("AWorldSettings")
            self._world = ws[0]["addr"] if ws else 0
        return self._world

    def _belongs(self, addr, roots):
        """Gehoert das Objekt zur Figur (selbst, Komponente oder Attribut-Set der Figur / ihres PlayerState)?"""
        mine = {roots["pawn"], roots["controller"], roots.get("state", 0)} - {0}
        cur = addr
        for _ in range(OUTER_DEPTH):
            if cur in mine:
                return True
            try:
                cur = self.live.outer(cur)
            except Exception:  # noqa: BLE001
                return False
            if not _valid(cur):
                return False
        return False

    # ------------------------------------------------------------------ Aufbau
    def build(self):
        """Eintraege aus dem SDK aufbauen und pruefen, ob die noetigen Klassen/Member existieren (noch nichts live)."""
        self.entries = []
        for spec in ENGINE:
            e = Entry(**spec)
            self._check_sdk(e)
            self.entries.append(e)
        self.entries += self._game_entries()
        self.by_key = {e.key: e for e in self.entries}
        return self.entries

    def _check_sdk(self, e):
        if self.sdk is None:
            e.status = "Kein SDK geladen"
            return
        m = self.sdk.find_member(e.cls, e.member)
        if m is None:
            e.status = f"{e.cls}.{e.member} gibt es in diesem Spiel nicht (SDK)"
            return
        e.offset = m.offset
        e.bit = getattr(m, "bit", -1) if e.bit < 0 else e.bit
        if not e.type:
            e.type = m.type
        for owner, member in e.steps:
            if self.sdk.find_member(owner, member) is None:
                e.status = f"{owner}.{member} gibt es in diesem Spiel nicht (SDK) - Kette zur Figur unterbrochen"
                return
        if Q.Target(e.cls, e.member, e.type, e.offset, e.bit).fmt is None:
            e.status = f"Typ {e.type} kann ich nicht schreiben"

    def _game_entries(self):
        import ue_profile as P
        import uecheat as C
        out = []
        if self.sdk is None:
            return out
        try:
            cands = C.find_candidates(self.sdk, min_score=6.0)
        except Exception as ex:  # noqa: BLE001
            self.log(f"Cheat-Menue: Kandidaten-Suche fehlgeschlagen: {ex}", "err")
            return out
        for cat, shown, kind in GAME_CATS:
            n = 0
            for c in cands:
                if c.category != cat or c.is_max or P.NOT_GAME.search(c.cls) or c.cls.startswith(("UWBP", "UABP")):
                    continue
                member = self.sdk.find_member(c.cls, c.member)
                got = Q.expand_member(self.sdk, c.cls, c.member, c.type, c.offset,
                                      member.bit if member else -1, cat, c.score)
                if not got:
                    continue
                t = got[0]
                e = Entry(key=f"g:{c.cls}.{t.member}", cat=shown, label=f"{c.cls}.{t.member}", kind=kind, cls=c.cls,
                          member=t.member, type=t.type, bit=t.bit, offset=t.offset, source="spiel", target=t,
                          on=True if kind == "toggle" else None, off=False if kind == "toggle" else None,
                          default="auto", note="; ".join(c.reasons[:2]))
                try:
                    e.companions = [(m.name, m.type, m.offset) for m in C.companions(self.sdk, c)][:2]
                except Exception:  # noqa: BLE001
                    e.companions = []
                out.append(e)
                n += 1
                if n >= PER_CAT:
                    break
        return out

    def check_live(self, progress=None):
        """Prueft gegen das laufende Spiel, welche Eintraege die Figur wirklich erreichen (setzt e.status)."""
        try:
            roots = self.roots(fresh=True)
        except MenuError as ex:
            for e in self.entries:
                if e.ok:
                    e.status = str(ex)
            return
        for i, e in enumerate(self.entries):
            if not e.ok:
                continue
            try:
                if not self.locate(e, roots):
                    e.status = "an der Figur nicht gefunden"
            except MenuError as ex:
                e.status = str(ex)
            except Exception as ex:  # noqa: BLE001
                e.status = f"nicht lesbar ({ex})"
            if progress:
                progress(i + 1, len(self.entries))

    # ------------------------------------------------------------------ Adressen
    def _target(self, e, off):
        if e.target is not None:                       # Wrapper-Struct (z. B. GAS-Attribut: Offset schon inkl. sub)
            t = e.target
            return Q.Target(t.cls, t.member, t.type, off, t.bit, t.category, t.score, t.parent, t.sub)
        return Q.Target(e.cls, e.member, e.type, off, e.bit)

    def locate(self, e, roots=None):
        """-> [(vaddr, Target)] der Werte dieses Eintrags an der Figur; MenuError mit Grund, wenn nichts da ist."""
        roots = roots or self.roots()
        if e.source == "spiel":
            t0 = e.target or Q.Target(e.cls, e.member, e.type, e.offset, e.bit)
            rows = [r for r in Q.find_instances(self.live, t0) if self._belongs(r["addr"], roots)]
            if not rows:
                raise MenuError("keine Instanz dieser Klasse an der Spielfigur")
            return [(r["vaddr"], self._target(e, r["off"])) for r in rows]
        obj = roots.get(e.root, 0)
        if not obj:
            raise MenuError(f"'{e.root}' nicht gefunden")
        for owner, member in e.steps:
            o = self._off(owner, member)
            if o is None:
                raise MenuError(f"{owner}.{member} nicht gefunden")
            obj = self._ptr(obj + o)
            if not obj:
                raise MenuError(f"{owner}.{member} ist leer (die Figur hat diese Komponente nicht)")
        off = self._off(e.cls, e.member)
        if off is None:
            raise MenuError(f"{e.cls}.{e.member} nicht gefunden")
        return [(obj + off, self._target(e, off))]

    # ------------------------------------------------------------------ Schalten
    def _remember(self, vaddr, t):
        if vaddr not in self._orig:
            try:
                self._orig[vaddr] = (t, Q.read_value(self._read, vaddr, t)[0])
            except Exception:  # noqa: BLE001
                pass

    def _write(self, vaddr, t, value):
        Q.write_value(self._read, self.client.write_memory, vaddr, t, value)

    def _auto_value(self, e, vaddr, t):
        """'auto': den Max-Wert derselben Instanz (Health -> MaxHealth), sonst den aktuellen Wert."""
        cur = Q.read_value(self._read, vaddr, t)[0]
        base = vaddr - t.offset
        best = cur
        for name, mtype, off in e.companions:
            ct = Q.Target(e.cls, name, mtype, off)
            if not ct.writable:
                continue
            try:
                v = Q.read_value(self._read, base + off, ct)[0]
            except Exception:  # noqa: BLE001
                continue
            if isinstance(v, (int, float)) and v > 0 and (best is None or v > best):
                best = v
        return best

    def set_toggle(self, key, on):
        e = self.by_key[key]
        if not e.ok:
            raise MenuError(e.status)
        if e.kind != "toggle":
            raise MenuError("Das ist ein Wert-Eintrag - Wert eintippen und SETZEN")
        roots = self.roots()
        locs = self.locate(e, roots)
        self._sig = {k: roots[k] for k in ("controller", "pawn", "state")}
        if not on:
            self.release(key)
            return len(locs)
        for vaddr, t in locs:
            self._remember(vaddr, t)
            self._write(vaddr, t, e.on)
            self.freezer.add(vaddr, t, e.on)
        e.addrs = [v for v, _t in locs]
        e.active = e.held = True
        for k in e.also:
            sub = self.by_key.get(k)
            if sub is not None and sub.ok:
                try:
                    self.set_toggle(k, on)
                except MenuError as ex:
                    self.log(f"Cheat-Menue: {sub.label}: {ex}", "info")
        return len(locs)

    def set_value(self, key, text, hold=True):
        e = self.by_key[key]
        if not e.ok:
            raise MenuError(e.status)
        if e.kind != "value":
            raise MenuError("Das ist ein Schalter - AN/AUS benutzen")
        roots = self.roots()
        locs = self.locate(e, roots)
        self._sig = {k: roots[k] for k in ("controller", "pawn", "state")}
        auto = (text or "").strip().lower() in AUTO
        for vaddr, t in locs:
            cur = Q.read_value(self._read, vaddr, t)[0]
            value = self._auto_value(e, vaddr, t) if auto else Q.parse_input(t, text, cur)
            if value is None:
                raise MenuError("Wert nicht lesbar")
            self._remember(vaddr, t)
            self._write(vaddr, t, value)
            if hold:
                self.freezer.add(vaddr, t, value)
            else:
                self.freezer.remove(vaddr)
        e.addrs = [v for v, _t in locs]
        e.active, e.held = True, bool(hold)
        return len(locs)

    def release(self, key, restore=True):
        """Eintrag freigeben: nicht mehr festhalten, Originalwert zurueckschreiben (nur wenn es noch dieselbe Figur ist)."""
        e = self.by_key[key]
        restore = restore and self.guard()
        for vaddr in e.addrs:
            self.freezer.remove(vaddr)
            orig = self._orig.pop(vaddr, None)
            if orig is not None and restore:
                try:
                    self._write(vaddr, orig[0], orig[1])
                except Exception as ex:  # noqa: BLE001
                    self.log(f"Cheat-Menue: {e.label}: Originalwert nicht zurueckgeschrieben: {ex}", "err")
        e.addrs = []
        e.active = e.held = False
        for k in e.also:
            if k in self.by_key and self.by_key[k].active:
                self.release(k, restore)

    def release_all(self, restore=True):
        for e in self.entries:
            if e.active:
                try:
                    self.release(e.key, restore)
                except Exception as ex:  # noqa: BLE001
                    self.log(f"Cheat-Menue: {e.label} nicht freigegeben: {ex}", "err")
        self.freezer.clear()
        if not restore:
            self._orig.clear()
        for e in self.entries:
            e.active = e.held = False
            e.addrs = []

    # ------------------------------------------------------------------ Festhalten
    def guard(self):
        """True, wenn die Figur noch dieselbe ist wie beim Aktivieren."""
        if not self._sig:
            return True
        o_pawn = self._off("AController", "Pawn")
        if o_pawn is None:
            o_pawn = self._off("APlayerController", "AcknowledgedPawn")
        try:
            return self._ptr(self._sig["controller"] + o_pawn) == self._sig["pawn"]
        except Exception:  # noqa: BLE001
            return False

    def tick(self):
        """Alle ~250 ms aufrufen.  -> None oder eine Meldung (z. B. Figur gewechselt -> alles freigegeben)."""
        if not len(self.freezer):
            return None
        if not self.guard():
            self.release_all(restore=False)          # alte Adressen NICHT mehr beschreiben
            return "Die Spielfigur hat gewechselt (Tod/Ladebildschirm) - alle Eintraege freigegeben. Neu aktivieren."
        self.freezer.tick(self.client)
        return None
