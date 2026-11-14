"""tools_cave_common.py - die SAMMLUNG der CAVEMAKER-Tabs (Unity und Unreal): gebaute Hooks sammeln, TEST AN / TEST AUS auf
der Konsole, und IN PROJEKT ÜBERNEHMEN.

Jeder Hook wird vor dem Speichern mit ReaperPys eigenem Parser und Cave-Assembler geprüft (cave_check.py), in den
Patch-Ordner geschrieben, noch einmal zurückgelesen und dann als normale Karte ins Hauptfenster übernommen
(gui.add_patch_from_file prüft ein drittes Mal mit ReapPatch.load).  Ein Hook, den ReaperPy nicht versteht, kommt gar
nicht erst so weit - er wird mit Begründung abgelehnt statt still übergangen.

Ein Eintrag ist ein "Patch-Objekt" mit: name, hook_addr, simple, aob, warnings, summary und to_json(author) -> Dokument.
(cavemaker.PatchDef erfüllt das; für Unreal-Dokumente gibt es DocPatch.)
"""
import os
import re
import tkinter as tk
from tkinter import messagebox

import cave_check as CC
import patch_engine as PE
from tools_common import ACCENT, BG, ERROR, TEXT_DIM, button, entry, label, tree, with_scroll


class DocPatch:
    """Ein fertiges .reapproj-Dokument (dict) als Patch-Objekt - z. B. aus ue_instr/cheatmenu_cave."""

    def __init__(self, doc, hook_addr, summary=""):
        self.doc, self.hook_addr, self.summary = doc, hook_addr, summary
        self.warnings = []
        rp = CC.load_doc(doc)
        self.name = rp.name
        self.simple = not PE.is_cave_patch(rp)
        self.aob = rp.origin_aob

    def to_json(self, author=""):
        d = dict(self.doc)
        if author:
            d["author"] = author
        return d


class Item:
    """Ein Eintrag der SAMMLUNG: gebauter Patch, geladener ReapPatch, Zustand auf der Konsole."""

    def __init__(self, pd, meta=None):
        self.pd, self.meta = pd, meta
        self.rp = self.state = None

    @property
    def kind(self):
        return "Patch" if self.pd.simple else "Cave"


class CaveCollectionMixin:
    """Für Tabs mit: self.win, self.log, self.bg, self.base, self._cfg und den Methoden _backend(), _out_dir()."""

    CFG_AUTHOR = "cave_author"
    LOG = "CAVEMAKER"

    def _build_collection(self, lower):
        self.items = []
        label(lower, "SAMMLUNG").pack(anchor="w")
        ct = tk.Frame(lower, bg=BG)
        ct.pack(fill="both", expand=True)
        self.coll = tree(ct, [("name", "PATCH"), ("typ", "ART"), ("addr", "HOOK"), ("state", "STATUS")],
                         [520, 70, 150, 110], height=4)
        self.coll.column("name", stretch=True)
        with_scroll(ct, self.coll)
        ar = tk.Frame(lower, bg=BG)
        ar.pack(fill="x", pady=4)
        button(ar, "TEST AN", self.test_on, accent=True).pack(side="left", padx=2)
        button(ar, "TEST AUS", self.test_off).pack(side="left", padx=2)
        button(ar, "ENTFERNEN", self.remove).pack(side="left", padx=2)
        self.coll_bar = ar
        label(ar, "AUTOR").pack(side="left", padx=(12, 2))
        self.v_author = tk.StringVar(value=self._cfg.get(self.CFG_AUTHOR, ""))
        entry(ar, self.v_author, 18).pack(side="left", padx=2)
        button(ar, "IN PROJEKT ÜBERNEHMEN", self.to_project, accent=True).pack(side="right", padx=2)
        self.lbl_done = label(lower, "", justify="left", anchor="w", wraplength=1000)
        self.lbl_done.pack(fill="x")

    def _author(self):
        return self.v_author.get().strip()

    def _backend(self):
        be = getattr(getattr(self.win, "app", None), "backend", None)
        if be is None or getattr(be, "client", None) is None:
            raise ValueError("Nicht verbunden - im Hauptfenster auf VERBINDEN klicken.")
        return be

    def _say(self, text, color=None):
        self.lbl_done.configure(text=text, fg=color or TEXT_DIM)

    def _used_hooks(self, skip=None):
        return {it.pd.hook_addr: it.pd.name for i, it in enumerate(self.items) if it is not None and i != skip}

    def _add_item(self, it, replace=None):
        vals = (it.pd.name, it.kind, f"{it.pd.hook_addr:#x}", "AN" if it.state else "aus")
        if replace is not None:
            self.items[replace] = it
            self.coll.item(str(replace), values=vals)
        else:
            self.items.append(it)
            self.coll.insert("", "end", iid=str(len(self.items) - 1), values=vals)
        self.log(f"{self.LOG}: Hinzugefügt: {it.pd.name}" + ("  (mit Signatur)" if it.pd.aob else ""), "ok")

    def _item(self):
        sel = self.coll.selection()
        if not sel:
            self.log(f"{self.LOG}: erst in der SAMMLUNG einen Eintrag wählen", "warn")
            return None, None
        return int(sel[0]), self.items[int(sel[0])]

    def _reapatch(self, it):
        if it.rp is None:
            it.rp = CC.load_doc(it.pd.to_json(self._author()))
        return it.rp

    def _after_test_on(self, it):
        """Haken für Unterklassen (z. B. Wirkung eines statischen Feldes prüfen)."""

    # ---- TEST AN / AUS ----
    def test_on(self):
        i, it = self._item()
        if it is None:
            return
        if it.state:
            return self.log(f"{self.LOG}: Dieser Patch ist schon an - erst TEST AUS.", "warn")
        try:
            be = self._backend()
        except ValueError as e:
            return self.log(f"{self.LOG}: {e}", "err")
        rp, hook = self._reapatch(it), it.pd.hook_addr

        def ok(st):
            it.state = st
            self.coll.set(str(i), "state", "AN")
            self.log(f"{self.LOG}: Test AN @ {hook:#x}: {it.pd.name}", "ok")
            self._after_test_on(it)

        self.bg(lambda: PE.apply_patch(be, rp, hook), ok, lambda e: self.log(f"{self.LOG}: Test: {e}", "err"))

    def test_off(self):
        i, it = self._item()
        if it is None:
            return
        if not it.state:
            return self.log(f"{self.LOG}: Dieser Patch ist nicht aktiv.", "warn")
        try:
            be = self._backend()
        except ValueError as e:
            return self.log(f"{self.LOG}: {e}", "err")
        rp, st = self._reapatch(it), it.state

        def ok(_r):
            it.state = None
            self.coll.set(str(i), "state", "aus")
            self.log(f"{self.LOG}: Test AUS: {it.pd.name}", "ok")

        self.bg(lambda: PE.deactivate_patch(be, rp, st), ok, lambda e: self.log(f"{self.LOG}: Zurücksetzen: {e}", "err"))

    def remove(self):
        i, it = self._item()
        if it is None:
            return
        if it.state:
            return self.log(f"{self.LOG}: Erst TEST AUS.", "warn")
        self.items[i] = None
        self.coll.delete(str(i))

    # ---- Ins Projekt ----
    def to_project(self):
        """Prüfen, schreiben, zurücklesen, als Karte ins Hauptfenster übernehmen."""
        sel = [int(i) for i in self.coll.selection()]
        pick = [(i, self.items[i]) for i in (sel or range(len(self.items))) if self.items[i] is not None]
        if not pick:
            return self.log(f"{self.LOG}: Die SAMMLUNG ist leer.", "warn")
        dup = {}
        for _i, it in pick:
            dup.setdefault(it.pd.hook_addr, []).append(it.pd.name)
        bad = [f"{h:#x}: " + ", ".join(n) for h, n in dup.items() if len(n) > 1]
        if bad:
            return messagebox.showerror("Projekt", "Diese Cheats benutzen denselben Haken und können so nicht gleichzeitig "
                                        "laufen:\n\n" + "\n".join(bad) + "\n\nEintrag wählen und einen anderen Haken nehmen.")
        try:
            be = self._backend()
        except ValueError as e:
            return self.log(f"{self.LOG}: {e}", "err")
        app, author = self.win.app, self._author()
        self._cfg[self.CFG_AUTHOR] = author
        self._save_cfg()
        out = self._out_dir()

        def job():
            done, failed = [], []
            for _i, it in pick:
                try:
                    path = CC.write_checked(out, it.pd.to_json(author), be, it.pd.hook_addr)
                    done.append((it, path))
                except (CC.CaveCheckError, OSError, ValueError) as e:
                    failed.append((it, str(e)))
            return done, failed

        def ok(res):
            done, failed = res
            added = []
            for it, path in done:
                try:
                    added.append(app.add_patch_from_file(path))
                except Exception as e:  # noqa: BLE001
                    failed.append((it, f"Hauptfenster: {e}"))
            lines = [f"✔ {len(added)} Hook(s) im Projekt - jeder wurde mit ReaperPys Parser und Cave-Assembler geprüft:"] \
                if added else ["✗ Es wurde kein Hook übernommen."]
            lines += [f"      {it.pd.name}  ({CC.describe(it.pd.to_json(author))})" for it, _p in done[:6]]
            lines += [f"✗ {it.pd.name}: {why}" for it, why in failed[:6]]
            self._say("\n".join(lines), ACCENT if added else ERROR)
            self.log(f"{self.LOG}: {len(added)} übernommen, {len(failed)} abgelehnt", "ok" if added else "err")

        self.bg(job, ok, lambda e: self.log(f"{self.LOG}: Projekt: {e}", "err"))

    def _save_cfg(self):
        """Unterklassen mit eigener Konfiguration überschreiben das."""


def safe_dirname(name):
    return re.sub(r"[^\w .()+-]", "_", name or "").strip() or "Spiel"


def out_dir_for(title, sub):
    import paths
    return os.path.join(paths.sub_dir("trainer"), safe_dirname(title), sub)
