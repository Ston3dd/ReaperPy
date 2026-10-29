"""tools_groups.py - Sammel-Tab: ein Reiter im Hauptnotebook, darin eigene Unterreiter (z. B. UNREAL, UNITY)."""
import tkinter as tk
from tkinter import ttk

BG = "#06080d"


class GroupTab(tk.Frame):
    """Rahmen mit eigenem Notebook.  Die Unterreiter werden mit `parent = group.nb` erzeugt und mit add() eingehaengt.
    `nb.group` zeigt zurueck auf den Rahmen - so findet ToolsWindow.show_tab den Weg nach oben."""

    def __init__(self, parent, win, title=""):
        super().__init__(parent, bg=BG)
        self.win, self.title_text = win, title
        self.nb = ttk.Notebook(self)
        self.nb.group = self
        self.nb.pack(fill="both", expand=True)

    def add(self, tab, text):
        self.nb.add(tab, text=text)
