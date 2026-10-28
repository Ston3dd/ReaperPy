"""Sammelt die deutschen UI-Texte der Werkzeug-Tabs per AST (fuer tests/test_tools_i18n.py)."""
import ast
import collections
import os
import re

HERE = os.path.join(os.path.dirname(__file__), "..")
FILES = ["tools_common.py", "tools_gui.py", "tools_scan_gui.py", "tools_sections_gui.py", "tools_items_gui.py", "tools_pointer_gui.py", "tools_debug_gui.py", "tools_extra_gui.py", "tools_ue_gui.py", "tools_uelive_gui.py", "tools_discover_gui.py", "tools_cheatmenu_gui.py", "tools_unity_gui.py", "cheatmenu.py", "script_tab.py", "klog_tab.py", "session.py", "tools_start_gui.py", "tools_ctx.py", "ue_profile.py"]
ALLCONST = {"tools_start_gui.py", "ue_profile.py"}
CTX = ("button", "label", "card", "clabel", "pbtn", "_check", "_small", "entry", "textbox", "tree", "tk.Label", "tk.Button", "tk.Checkbutton", "tk.Radiobutton", "tk.LabelFrame",
       "ttk.Label", "ttk.Button", "ttk.Checkbutton", "ttk.LabelFrame", "ttk.Radiobutton", "add", "heading", "configure", "config", "set",
       "log", "showinfo", "showerror", "showwarning", "askyesno", "askokcancel", "askyesnocancel", "askstring", "askinteger",
       "asksaveasfilename", "askopenfilename", "askdirectory", "insert", "add_command", "add_cascade", "add_checkbutton", "_toast",
       "_ilog", "on_log", "_state", "_tr", "tr", "_sug", "append", "log_msg", "tab", "title")
IGN = re.compile(r"^([a-z_][a-z0-9_\.]*|[A-Z][a-z]+\d*|[A-Za-z]+:|\W+|\d+.*\d|0x[0-9A-Fa-f]+|<<.*>>|<.*>|#[0-9a-fA-F]{6}|"
                 r".*\.(py|json|txt|md|csv|ico|png)|%[^ ]*)$")


def _callname(n):
    if isinstance(n, ast.Name):
        return n.id
    if isinstance(n, ast.Attribute):
        return n.attr
    return ""


def _letters(s):
    return bool(re.search(r"[A-Za-zÄÖÜäöüß]{3}", s))


def harvest(path):
    with open(os.path.join(HERE, path), encoding="utf-8") as f:
        t = ast.parse(f.read())
    out = collections.OrderedDict()
    if path in ALLCONST:
        for c in ast.walk(t):
            if isinstance(c, ast.Constant) and isinstance(c.value, str):
                v = c.value
                if _letters(v) and "(?" not in v and "\\" not in v and not (
                        len(v) > 160 and "\n" in v and path == "ue_profile.py" and v.lstrip().startswith(("ue_profile", '"""'))):
                    out[v.strip("\n")] = 1
        return list(out)

    def consts(node):
        for c in ast.walk(node):
            if isinstance(c, ast.Constant) and isinstance(c.value, str) and _letters(c.value):
                out[c.value.strip("\n")] = 1
    for n in ast.walk(t):
        if isinstance(n, ast.Call) and _callname(n.func) in CTX:
            for a in list(n.args) + [k.value for k in n.keywords if k.arg in ("text", "title", "message", "prompt", "label", "values")]:
                consts(a)
        elif isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call):
            for a in n.exc.args:
                consts(a)
    return list(out)


def missing(en_keys):
    """Alle Texte, die weder uebersetzt noch als technisch/gleichlautend markiert sind."""
    miss = []
    for f in FILES:
        if not os.path.exists(os.path.join(HERE, f)):
            continue
        for s in harvest(f):
            if f == "ue_profile.py" and re.search(r"[|^$\[]", s):
                continue
            if f == "ue_profile.py" and re.fullmatch(r"[a-z_]+(\.[a-z_]+)*", s):
                continue
            if IGN.match(s.strip()) or s in en_keys:
                continue
            miss.append((f, s))
    return miss
