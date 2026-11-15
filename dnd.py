"""dnd.py - Dateien per Drag & Drop ins Fenster ziehen (optional).

Braucht das Zusatzpaket `tkinterdnd2` (pip install tkinterdnd2).  Fehlt es oder klappt die Einbindung nicht,
passiert nichts - dann bleiben die Knopf-Dialoge (PATCH HINZUFUEGEN) der einzige Weg.
"""


def available():
    try:
        import tkinterdnd2  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def enable(root, widgets, callback):
    """callback(list_of_paths) bei jedem Drop auf eines der Widgets.  -> True, wenn Drag & Drop aktiv ist."""
    try:
        from tkinterdnd2 import TkinterDnD, DND_FILES
        TkinterDnD._require(root)
    except Exception:  # noqa: BLE001
        return False

    def on_drop(event):
        try:
            paths = [p for p in root.tk.splitlist(event.data) if p]
        except Exception:  # noqa: BLE001
            paths = []
        if paths:
            callback(paths)
        return event.action

    ok = False
    for w in widgets:
        try:
            w.drop_target_register(DND_FILES)
            w.dnd_bind("<<Drop>>", on_drop)
            ok = True
        except Exception:  # noqa: BLE001
            continue
    return ok
