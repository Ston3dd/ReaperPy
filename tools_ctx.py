"""tools_ctx.py - Rechtsklick-Menues fuer das ganze Programm (Listen, Eingabefelder, Textfelder).

install(root) bindet die Menues klassenweit (bind_class): sie gelten fuer alle vorhandenen UND spaeter erzeugten
Treeviews, Entries und Textfelder.  Listen, die schon ein eigenes Menue haben (tools_common.tree(actions=...)), behalten es.
Die Menue-Inhalte stehen in reinen Funktionen (tree_items/entry_items/text_items) und sind ohne Oberflaeche testbar.
"""
import csv
import io
import re
import tkinter as tk

ADDR_RE = re.compile(r"^(?:base\s*[+-]\s*)?(?:0x)?([0-9A-Fa-f]{5,16})$|^base\s*[+-]\s*0x[0-9A-Fa-f]+$")
BG_CARD, BG_HVR, TEXT, ACCENT = "#14192b", "#1c2340", "#e8f0ff", "#22e6c4"


def _tr(s):
    try:
        import tools_i18n
        return tools_i18n.tr(s)
    except Exception:  # noqa: BLE001
        return s


def looks_like_address(text):
    return bool(ADDR_RE.match(str(text).strip()))


def addr_value(text, base=0):
    t = str(text).strip().lower().replace(" ", "")
    if t.startswith("base"):
        sign = -1 if "-" in t[4:5] else 1
        return base + sign * int(t[5:], 16)
    return int(t[2:] if t.startswith("0x") else t, 16)


def copy_text(widget, text):
    widget.clipboard_clear()
    widget.clipboard_append(text)


def _column_id(tv, x):
    try:
        col = tv.identify_column(x)               # "#3"
        idx = int(col.lstrip("#")) - 1
        cols = [str(c) for c in tv["columns"]]
        return cols[idx] if 0 <= idx < len(cols) else None
    except Exception:  # noqa: BLE001
        return None


def tree_items(tv, x, y, win=None):
    """Standard-Menue einer Liste -> [(Text, Funktion)] ((None, None) = Trennlinie)."""
    iid = tv.identify_row(y)
    if iid and iid not in tv.selection():
        tv.selection_set(iid)
    sel = list(tv.selection())
    cols = [str(c) for c in tv["columns"]]
    heads = [tv.heading(c, "text") for c in cols]
    items = []
    cell = ""
    cid = _column_id(tv, x)
    if iid and cid is not None:
        try:
            cell = str(tv.set(iid, cid))
        except Exception:  # noqa: BLE001
            cell = ""
    if sel:
        def rows_text():
            return "\n".join("\t".join(str(v) for v in tv.item(i, "values")) for i in sel)
        items.append((_tr("Zeile kopieren") if len(sel) == 1 else _tr("Zeilen kopieren"), lambda: copy_text(tv, rows_text())))
    if cell:
        items.append((_tr("Zelle kopieren"), lambda: copy_text(tv, cell)))
    if win is not None and cell and looks_like_address(cell):
        base = getattr(getattr(win, "app", None), "IMAGE_BASE", 0) or 0
        try:
            a = addr_value(cell, base)
        except ValueError:
            a = None
        if a is not None:
            if hasattr(win, "goto_memory"):
                items.append((_tr("Im Speicher öffnen"), lambda: win.goto_memory(a)))
            if hasattr(win, "goto_disasm"):
                items.append((_tr("Im Disassembler öffnen"), lambda: win.goto_disasm(a)))
    if tv.get_children():
        if items:
            items.append((None, None))

        def all_csv():
            buf = io.StringIO()
            w = csv.writer(buf, lineterminator="\n")
            w.writerow(heads)
            for i in tv.get_children():
                w.writerow(tv.item(i, "values"))
            return buf.getvalue()
        items.append((_tr("Alle Zeilen kopieren (CSV)"), lambda: copy_text(tv, all_csv())))
        items.append((_tr("Alles auswählen"), lambda: tv.selection_set(tv.get_children())))
    return items


def entry_items(w):
    gen = lambda ev: (lambda: w.event_generate(ev))  # noqa: E731
    return [(_tr("Ausschneiden"), gen("<<Cut>>")), (_tr("Kopieren"), gen("<<Copy>>")), (_tr("Einfügen"), gen("<<Paste>>")),
            (None, None), (_tr("Alles markieren"), lambda: _select_all_entry(w)), (_tr("Feld leeren"), lambda: _clear_entry(w))]


def _select_all_entry(w):
    try:
        w.select_range(0, "end")
        w.icursor("end")
    except Exception:  # noqa: BLE001
        pass


def _clear_entry(w):
    try:
        if str(w.cget("state")) in ("disabled", "readonly"):
            return
        w.delete(0, "end")
    except Exception:  # noqa: BLE001
        pass


def text_items(w, save_dialog=None):
    """Textfeld/Log: Kopieren, Alles markieren; bei bearbeitbaren Feldern auch Einfuegen/Ausschneiden."""
    editable = True
    try:
        editable = str(w.cget("state")) == "normal"
    except Exception:  # noqa: BLE001
        pass
    items = [(_tr("Kopieren"), lambda: w.event_generate("<<Copy>>"))]
    if editable:
        items = [(_tr("Ausschneiden"), lambda: w.event_generate("<<Cut>>"))] + items + \
                [(_tr("Einfügen"), lambda: w.event_generate("<<Paste>>"))]
    items.append((_tr("Alles markieren"), lambda: (w.tag_add("sel", "1.0", "end-1c"), "break")))
    if getattr(w, "_is_log", False):
        items.append((None, None))
        items.append((_tr("Log leeren"), lambda: _clear_text(w)))
        if save_dialog:
            items.append((_tr("Log speichern…"), save_dialog))
    return items


def _clear_text(w):
    try:
        w.configure(state="normal")
        w.delete("1.0", "end")
        w.configure(state="disabled")
    except Exception:  # noqa: BLE001
        pass


def show_menu(widget, event, items):
    items = [i for i in items if i]
    if not items:
        return
    m = tk.Menu(widget, tearoff=0, bg=BG_CARD, fg=TEXT, activebackground=BG_HVR, activeforeground=ACCENT)
    for text, fn in items:
        if text is None:
            m.add_separator()
        else:
            m.add_command(label=text, command=fn)
    try:
        m.tk_popup(event.x_root, event.y_root)
    finally:
        try:
            m.grab_release()
        except Exception:  # noqa: BLE001
            pass


def _win_of(widget):
    top = widget.winfo_toplevel()
    return top if hasattr(top, "goto_memory") else None


def on_tree(event):
    tv = event.widget
    if getattr(tv, "_has_ctx", False):             # eigenes Menue vorhanden
        return None
    show_menu(tv, event, tree_items(tv, event.x, event.y, _win_of(tv)))
    return "break"


def on_entry(event):
    w = event.widget
    try:
        w.focus_set()
    except Exception:  # noqa: BLE001
        pass
    show_menu(w, event, entry_items(w))
    return "break"


def on_text(event):
    w = event.widget
    if getattr(w, "_has_ctx", False):
        return None
    try:
        w.focus_set()
    except Exception:  # noqa: BLE001
        pass
    show_menu(w, event, text_items(w, getattr(w, "_save_log", None)))
    return "break"


def install(root):
    """Rechtsklick (Windows/Linux Button-3, macOS Button-2) klassenweit binden - idempotent."""
    if getattr(root, "_ctx_installed", False):
        return
    for seq in ("<Button-3>", "<Button-2>"):
        root.bind_class("Treeview", seq, on_tree, add="+")
        for cls in ("Entry", "TEntry", "TCombobox", "Spinbox"):
            root.bind_class(cls, seq, on_entry, add="+")
        root.bind_class("Text", seq, on_text, add="+")
    root._ctx_installed = True
