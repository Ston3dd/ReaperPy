"""Minimal-Ersatz fuer tkinter (nur fuer Smoke-Tests ohne Display): jedes Widget akzeptiert jeden
Aufruf; Variablen und Treeview speichern Werte."""
import sys, types

class W:
    def __init__(self, *a, **k): self._k = k
    def __getattr__(self, n):
        if n.startswith("__"): raise AttributeError(n)
        return lambda *a, **k: W()
    def winfo_exists(self): return True
    def winfo_children(self): return []
    def winfo_ismapped(self): return True
    def after(self, *a, **k): return "id"
    def index(self, *a): return "1.0"
    def cget(self, k): return getattr(self, "_text", "")
    def configure(self, **k):
        if "text" in k: self._text = k["text"]
    config = configure
    def __getitem__(self, k): return 0
    def __setitem__(self, k, v): pass

class Var:
    def __init__(self, master=None, value=None, **k): self.v = "" if value is None else value
    def get(self): return self.v
    def set(self, v): self.v = v

class Tree(W):
    def __init__(self, *a, **k): self.rows = {}; self.sel = (); self._n = 0
    def insert(self, parent, idx, iid=None, values=(), **k):
        iid = iid or f"I{self._n}"; self._n += 1; self.rows[iid] = tuple(values); return iid
    def delete(self, *ids):
        for i in (ids or ()): self.rows.pop(i, None)
    def get_children(self, *a): return tuple(self.rows)
    def selection(self): return self.sel
    def item(self, iid, opt=None, **k):
        if "values" in k: self.rows[iid] = tuple(k["values"]); return None
        return self.rows[iid] if opt == "values" else {}
    def selection_set(self, ids): self.sel = tuple(ids)

def install():
    if getattr(sys.modules.get("tkinter"), "_GHOST", False):      # schon installiert -> nicht ersetzen
        return
    tk = types.ModuleType("tkinter"); ttk = types.ModuleType("tkinter.ttk")
    mb = types.ModuleType("tkinter.messagebox"); fd = types.ModuleType("tkinter.filedialog")
    sd = types.ModuleType("tkinter.simpledialog")
    for n in ("Frame", "Label", "Button", "Entry", "Text", "Toplevel", "Checkbutton", "Listbox", "Canvas",
              "Scrollbar", "Tk", "Menu", "Radiobutton", "LabelFrame", "PanedWindow", "Scale", "Spinbox"):
        setattr(tk, n, type(n, (W,), {}))
    tk.StringVar = tk.BooleanVar = tk.IntVar = tk.DoubleVar = Var
    for n in ("Notebook", "Combobox", "Scrollbar", "PanedWindow", "Style", "Progressbar", "Frame", "Label",
              "Button", "Entry", "Separator"):
        setattr(ttk, n, type(n, (W,), {}))
    ttk.Treeview = Tree
    mb.askyesno = lambda *a, **k: True; mb.showerror = mb.showinfo = mb.showwarning = lambda *a, **k: None
    mb.askokcancel = mb.askyesno
    mb.askyesnocancel = lambda *a, **k: True
    fd.asksaveasfilename = fd.askopenfilename = lambda *a, **k: ""
    fd.askdirectory = lambda *a, **k: ""
    sd.askstring = lambda *a, **k: None
    tk.ttk, tk.messagebox, tk.filedialog, tk.simpledialog = ttk, mb, fd, sd
    tk._GHOST = True
    tk.END = "end"; tk.NORMAL = "normal"; tk.DISABLED = "disabled"
    sys.modules.update({"tkinter": tk, "tkinter.ttk": ttk, "tkinter.messagebox": mb,
                        "tkinter.filedialog": fd, "tkinter.simpledialog": sd})
