"""tools_debug_gui.py – Debugger-Tab für das Werkzeug-Fenster."""
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import ps5_ext as X
from debugger import DebugSession, DebugError
from tools_common import (BG, BG_CARD, ACCENT, TEXT, TEXT_DIM, WARN, ERROR, FONT_LABEL,
                          BaseTab, button, label, entry, tree, with_scroll, hexs)

WP_TYPES = {"schreiben": X.WP_WRITE, "lesen/schreiben": X.WP_RDWR, "ausführen": X.WP_EXEC}


class DebugTab(BaseTab):
    def __init__(self, parent, win):
        super().__init__(parent, win)
        self.sess = None
        self.hit_items = {}          # iid -> hit-Paket

        top = tk.Frame(self, bg=BG); top.pack(fill="x", padx=8, pady=(8, 4))
        button(top, "ATTACH", self.attach, accent=True).pack(side="left", padx=2)
        button(top, "DETACH", self.detach).pack(side="left", padx=2)
        self.lbl = label(top, "nicht attached"); self.lbl.pack(side="left", padx=10)

        run = tk.Frame(self, bg=BG); run.pack(fill="x", padx=8, pady=2)
        button(run, "▶ WEITER", lambda: self._do(lambda: self.sess.resume()), accent=True).pack(side="left", padx=2)
        button(run, "⤵ STEP", lambda: self._do(lambda: self.sess.step())).pack(side="left", padx=2)
        button(run, "⤼ STEP OVER", lambda: self._do(lambda: self.sess.step_over())).pack(side="left", padx=2)
        button(run, "⤴ STEP OUT", lambda: self._do(lambda: self.sess.step_out())).pack(side="left", padx=2)
        button(run, "■ ANHALTEN", lambda: self._do(lambda: self.sess.halt())).pack(side="left", padx=2)
        label(run, "THREAD").pack(side="left", padx=(16, 4))
        self.v_thr = tk.StringVar()
        self.cb_thr = ttk.Combobox(run, textvariable=self.v_thr, width=26, state="readonly")
        self.cb_thr.pack(side="left")
        self.cb_thr.bind("<<ComboboxSelected>>", lambda _e: self.refresh_regs())
        button(run, "THREADS", self.refresh_threads).pack(side="left", padx=2)
        button(run, "REGISTER", self.refresh_regs).pack(side="left", padx=2)
        button(run, "STACK", self.show_stack).pack(side="left", padx=2)
        button(run, "STACK-SCAN", self.show_stack_scan).pack(side="left", padx=2)

        mid = tk.Frame(self, bg=BG); mid.pack(fill="both", expand=True, padx=8, pady=4)
        left = tk.Frame(mid, bg=BG); left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(mid, bg=BG); right.pack(side="left", fill="both", padx=(8, 0))

        # Breakpoints
        row = tk.Frame(left, bg=BG); row.pack(fill="x")
        label(row, "BREAKPOINT @").pack(side="left")
        self.v_bp = tk.StringVar()
        entry(row, self.v_bp, 20).pack(side="left", padx=6)
        button(row, "SETZEN", self.add_bp, accent=True).pack(side="left", padx=2)
        button(row, "ENTFERNEN", self.del_bp).pack(side="left", padx=2)
        self.bpt = tree(left, [("i", "#"), ("a", "ADRESSE"), ("o", "OFFSET"), ("on", "AN")],
                        [40, 170, 100, 50], height=5)
        self.bpt.pack(fill="x", pady=(2, 6))

        # Watchpoints
        row = tk.Frame(left, bg=BG); row.pack(fill="x")
        label(row, "WATCHPOINT @").pack(side="left")
        self.v_wp = tk.StringVar()
        entry(row, self.v_wp, 20).pack(side="left", padx=6)
        self.v_wsize = tk.StringVar(value="4")
        ttk.Combobox(row, textvariable=self.v_wsize, values=["1", "2", "4", "8"],
                     width=3, state="readonly").pack(side="left")
        self.v_wtype = tk.StringVar(value="schreiben")
        ttk.Combobox(row, textvariable=self.v_wtype, values=list(WP_TYPES), width=14,
                     state="readonly").pack(side="left", padx=4)
        button(row, "SETZEN", self.add_wp, accent=True).pack(side="left", padx=2)
        button(row, "ENTFERNEN", self.del_wp).pack(side="left", padx=2)
        self.wpt = tree(left, [("i", "#"), ("a", "ADRESSE"), ("s", "GRÖSSE"), ("t", "TYP")],
                        [40, 170, 70, 130], height=4)
        self.wpt.pack(fill="x", pady=(2, 6))

        # Treffer
        label(left, "TREFFER (Klick = Register dieses Treffers)").pack(anchor="w")
        fr = tk.Frame(left, bg=BG); fr.pack(fill="both", expand=True)
        self.hits = tree(fr, [("t", "ZEIT"), ("k", "ART"), ("a", "ADRESSE"), ("th", "THREAD"), ("n", "ANZAHL")],
                         [80, 70, 170, 90, 70], height=8)
        with_scroll(fr, self.hits)
        self.hits.bind("<<TreeviewSelect>>", self._hit_sel)

        # Register
        label(right, "REGISTER (Doppelklick = ändern)").pack(anchor="w")
        self.regs = tree(right, [("r", "REG"), ("v", "WERT")], [70, 170], height=20)
        self.regs.pack(fill="y", expand=True)
        self.regs.bind("<Double-1>", self._edit_reg)
        self.lbl_stack = label(right, "")

    # ---- Hilfen ----
    def _need(self):
        if not self.sess or not self.sess.attached:
            self.log("Erst ATTACH", "warn")
            return False
        return True

    def _do(self, fn):
        if not self._need():
            return
        self.bg(fn, lambda _r: None)

    def _lwp(self):
        t = self.v_thr.get()
        return int(t.split()[0]) if t else None

    # ---- Attach / Detach ----
    def attach(self):
        if self.sess and self.sess.attached:
            return self.log("Schon attached", "warn")
        be = self.win.app.backend
        if be.pid is None:
            return self.log("Haupt-Fenster nicht verbunden", "err")
        if not messagebox.askyesno(
                "Debugger", "Debugger an das Spiel hängen?\n\n• Das Spiel kann dabei kurz hängen.\n"
                            "• Windows-Firewall muss eingehend Port 755 erlauben.\n"
                            "• Beim Beenden bitte DETACH benutzen."):
            return
        sess = DebugSession(be.host, be.port, be.pid, on_hit=self._on_hit_thread,
                            on_log=lambda m: self.win.ui(lambda: self.log(m, "info")),
                            on_state=lambda st: self.win.ui(lambda: self._state(st)))
        self.win.app.debug_busy = True            # Waechter des Hauptfensters pausiert, solange attached wird / attached ist

        def job():
            sess.attach()
            return sess

        def failed(e):
            self.win.app.debug_busy = False
            self.log(str(e), "err")
        self.bg(job, self._attached, failed)

    def _state(self, st):
        """Rueckmeldungen der Session (Keep-Alive / Wiederaufbau) ins Label."""
        self._notify_state(st)
        if st == "attached" and self.sess is not None:
            self.lbl.configure(text=f"attached  PID {self.sess.pid}", fg=ACCENT)
        elif st == "reconnecting":
            self.lbl.configure(text="Verbindung wird neu aufgebaut …", fg=TEXT_DIM)
        elif st == "lost":
            self.win.app.debug_busy = False
            self.lbl.configure(text="Verbindung verloren - DETACH, dann neu attachen", fg="#ff5555")
        elif st == "detached":
            self.win.app.debug_busy = False

    def _notify_state(self, st):
        """Debugger-Zustand auf dem PS5-Bildschirm melden (ps5_notify.py; Fehler bleiben folgenlos)."""
        try:
            pid = self.sess.pid if self.sess is not None else getattr(self.win.app.backend, "pid", None)
            self.win.app.notifier.debugger(st, pid)
        except Exception:  # noqa: BLE001
            pass

    def _attached(self, sess):
        self.sess = sess
        self.lbl.configure(text=f"attached  PID {sess.pid}", fg=ACCENT)
        self.refresh_threads()
        self._self_test(0.5)
        self._self_test(3.0)

    def _self_test(self, delay):
        """Nach dem Attach zweimal pruefen und ins Log schreiben, welche Verbindung antwortet (Diagnose bei Abbruechen)."""
        def run():
            time.sleep(delay)
            s = self.sess
            if not s or not s.attached:
                return None
            return s.health(getattr(self.win.app.backend, "client", None))

        def show(h):
            if h is None:
                return
            self.log("Selbsttest: Debug-Verbindung " + ("OK" if h["debug_ping"] else "ANTWORTET NICHT")
                     + ", Haupt-Verbindung " + {True: "OK", False: "ANTWORTET NICHT", None: "-"}[h["main_ping"]]
                     + ", Rueckkanal " + ("steht" if h["back_channel"] else "fehlt (Firewall Port 755?)")
                     + (f", {h['reconnects']}x neu aufgebaut" if h["reconnects"] else ""),
                     "info" if h["debug_ping"] and h["main_ping"] is not False else "err")
        self.bg(run, show)

    def detach(self):
        s = self.sess
        if not s:
            return
        self.win.app.debug_busy = False
        self.bg(s.detach, lambda _r: (self.lbl.configure(text="nicht attached", fg=TEXT_DIM),
                                      self.bpt.delete(*self.bpt.get_children()),
                                      self.wpt.delete(*self.wpt.get_children())))

    def shutdown(self):
        if self.sess and self.sess.attached:
            try:
                self.sess.detach()
            except Exception:
                pass

    # ---- Breakpoints ----
    def add_bp(self):
        if not self._need():
            return
        try:
            a = self.addr(self.v_bp.get())
            idx = self.sess.free_bp_index()
        except Exception as e:
            return self.log(str(e), "err")
        self.bg(lambda: self.sess.set_breakpoint(idx, a), lambda _r: self._fill_bps())

    def del_bp(self):
        sel = self.bpt.selection()
        if not sel or not self._need():
            return
        idx = int(self.bpt.item(sel[0], "values")[0])
        self.bg(lambda: self.sess.clear_breakpoint(idx), lambda _r: self._fill_bps())

    def _fill_bps(self):
        self.bpt.delete(*self.bpt.get_children())
        for i, b in sorted(self.sess.bps.items()):
            self.bpt.insert("", "end", values=(i, f"{b['addr']:016X}", f"+{b['addr'] - self.base:X}",
                                               "ja" if b["enabled"] else "nein"))

    # ---- Watchpoints ----
    def add_wp(self):
        if not self._need():
            return
        try:
            a = self.addr(self.v_wp.get())
            idx = self.sess.free_wp_index()
            size = int(self.v_wsize.get())
            typ = WP_TYPES[self.v_wtype.get()]
            if typ == X.WP_EXEC:
                size = 1                      # x86: Ausführungs-Watchpoints sind immer 1 Byte
            if a % size:
                raise ValueError(f"Adresse {a:#x} muss auf {size} Byte ausgerichtet sein (Hardware-Watchpoint)")
        except Exception as e:
            return self.log(str(e), "err")
        self.bg(lambda: self.sess.set_watchpoint(idx, a, size, typ), lambda _r: self._fill_wps())

    def del_wp(self):
        sel = self.wpt.selection()
        if not sel or not self._need():
            return
        idx = int(self.wpt.item(sel[0], "values")[0])
        self.bg(lambda: self.sess.clear_watchpoint(idx), lambda _r: self._fill_wps())

    def _fill_wps(self):
        self.wpt.delete(*self.wpt.get_children())
        names = {v: k for k, v in WP_TYPES.items()}
        for i, w in sorted(self.sess.wps.items()):
            self.wpt.insert("", "end", values=(i, f"{w['addr']:016X}", w["size"], names.get(w["type"], "?")))

    # ---- Treffer (kommen aus dem Listener-Thread) ----
    def _on_hit_thread(self, hit):
        try:
            self.win.app.notifier.hit(hit["kind"], hit["addr"])
        except Exception:  # noqa: BLE001
            pass
        self.win.ui(lambda: self._show_hit(hit))

    def _show_hit(self, hit):
        iid = self.hits.insert("", 0, values=(
            time.strftime("%H:%M:%S", time.localtime(hit["time"])), hit["kind"],
            f"{hit['addr']:016X}", hit["lwpid"], hit["count"]))
        self.hit_items[iid] = hit
        self.hits.selection_set(iid)
        self._fill_regs(hit["regs"])
        self.log(f"{hit['kind']} @ {hit['addr']:#x}  Thread {hit['lwpid']}  (#{hit['count']})", "warn")
        self.refresh_threads(select=hit["lwpid"])

    def _hit_sel(self, _e):
        sel = self.hits.selection()
        if sel and sel[0] in self.hit_items:
            self._fill_regs(self.hit_items[sel[0]]["regs"])

    # ---- Threads / Register / Stack ----
    def refresh_threads(self, select=None):
        if not self._need():
            return

        def ok(ths):
            vals = [f"{t['lwpid']}  {t['name']}" for t in ths]
            self.cb_thr["values"] = vals
            pick = next((v for v in vals if select and v.startswith(str(select))), None)
            if pick:
                self.v_thr.set(pick)
            elif not self.v_thr.get() and vals:
                self.v_thr.set(vals[0])
        self.bg(lambda: self.sess.threads(), ok)

    def refresh_regs(self):
        if not self._need() or self._lwp() is None:
            return
        lw = self._lwp()
        self.bg(lambda: self.sess.regs(lw), self._fill_regs)

    def _fill_regs(self, regs):
        self.regs.delete(*self.regs.get_children())
        for n in X.REG_SHOW_ORDER:
            self.regs.insert("", "end", values=(n, f"{regs[n]:016X}"))

    def _edit_reg(self, _e):
        sel = self.regs.selection()
        if not sel or not self._need() or self._lwp() is None:
            return
        name, cur = self.regs.item(sel[0], "values")
        txt = simpledialog.askstring("Register ändern", f"{name} = (hex)", initialvalue=cur, parent=self)
        if not txt:
            return
        try:
            val = int(txt, 16)
        except ValueError:
            return self.log("Ungültiger Hex-Wert", "err")
        lw = self._lwp()
        self.bg(lambda: self.sess.set_reg(lw, name, val), lambda _r: self.refresh_regs())

    def show_stack(self):
        if not self._need() or self._lwp() is None:
            return
        lw = self._lwp()

        def ok(frames):
            d = tk.Toplevel(self); d.title("Call-Stack"); d.configure(bg=BG)
            tv = tree(d, [("n", "#"), ("ret", "RÜCKSPRUNG"), ("off", "OFFSET"), ("rbp", "RBP")],
                      [40, 170, 110, 170], height=16)
            tv.pack(fill="both", expand=True, padx=8, pady=8)
            for i, f in enumerate(frames):
                tv.insert("", "end", values=(i, f"{f['ret']:016X}", f"+{f['ret'] - self.base:X}",
                                             f"{f['rbp']:016X}"))
            tv.bind("<Double-1>", lambda _e: tv.selection() and self.win.goto_disasm(
                int(tv.item(tv.selection()[0], "values")[1], 16)))
        self.bg(lambda: self.sess.stack(lw), ok)

    def show_stack_scan(self):
        """Aufrufkette auch ohne Frame-Pointer: Stack nach Rueckkehradressen hinter CALLs absuchen."""
        if not self._need() or self._lwp() is None:
            return
        lw = self._lwp()
        import aob as AOB
        import unwind

        def job():
            rsp = self.sess.regs(lw)["rsp"]
            cl = self.win.client
            ex = AOB.exec_regions(cl.get_maps(), 0x1000)
            in_code = lambda a: any(s <= a < e for s, e in ex)
            return rsp, unwind.unwind(cl.read_memory, rsp, in_code, depth=0x1000, max_frames=48)

        def ok(res):
            rsp, frames = res
            d = tk.Toplevel(self); d.title("Call-Stack (Stack-Scan)"); d.configure(bg=BG)
            label(d, "Kandidaten - Treffer koennen auch alte Rahmen sein. Doppelklick = Disassembler an der "
                     "Aufrufstelle.").pack(anchor="w", padx=8, pady=(8, 0))
            tv = tree(d, [("n", "#"), ("slot", "STACK +RSP"), ("ret", "RUECKSPRUNG"), ("off", "OFFSET"),
                          ("call", "AUFRUFSTELLE")], [40, 100, 170, 110, 170], height=18)
            tv.pack(fill="both", expand=True, padx=8, pady=8)
            for i, f in enumerate(frames):
                tv.insert("", "end", values=(i, f"+{f['slot'] - rsp:X}", f"{f['ret']:016X}",
                                             f"+{f['ret'] - self.base:X}", f"{f['callsite']:016X}"))
            tv.bind("<Double-1>", lambda _e: tv.selection() and self.win.goto_disasm(
                int(tv.item(tv.selection()[0], "values")[4], 16)))
            self.log(f"Stack-Scan: {len(frames)} Rueckkehr-Kandidaten", "ok")
        self.bg(job, ok)
