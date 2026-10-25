"""GUI for Universal Unreal Dump Analyzer; read-only static discovery."""
import os, threading, tkinter as tk
from tkinter import ttk, filedialog, messagebox
from universal_analyzer import analyze_dump, export_report, export_csv, default_checkpoint_path
from tools_common import BG, BG_BAR, BG_CARD, ACCENT, TEXT, TEXT_DIM, WARN, FONT_MONO, FONT_HEAD, FONT_LABEL, button, label, tree, with_scroll

class UniversalAnalyzerTab(tk.Frame):
    def __init__(self,parent,win):
        super().__init__(parent,bg=BG); self.win=win; self.report=None; self.cancel_event=None; self.scanning=False
        top=tk.Frame(self,bg=BG);top.pack(fill='x',padx=8,pady=8)
        label(top,'DUMP / SDK').pack(side='left')
        self.path=tk.StringVar()
        tk.Entry(top,textvariable=self.path,bg=BG_CARD,fg=TEXT,insertbackground=TEXT,width=62,relief='flat').pack(side='left',fill='x',expand=True,padx=6,ipady=5)
        button(top,'ORDNER…',self.pick_folder).pack(side='left',padx=2)
        button(top,'ZIP…',self.pick_zip).pack(side='left',padx=2)
        button(top,'SCAN / FORTSETZEN',self.scan,accent=True).pack(side='left',padx=2)
        button(top,'ABBRECHEN',self.cancel_scan).pack(side='left',padx=2)
        button(top,'NEU SCANNEN',self.restart_scan).pack(side='left',padx=2)
        row=tk.Frame(self,bg=BG);row.pack(fill='x',padx=8)
        self.status=tk.StringVar(value='Wähle einen Dump-Ordner oder eine SDK-ZIP. Der Scan arbeitet lokal und nur lesend.')
        tk.Label(row,textvariable=self.status,bg=BG,fg=WARN,font=FONT_LABEL,anchor='w').pack(side='left',fill='x',expand=True)
        button(row,'JSON EXPORT',self.save_json).pack(side='right',padx=2)
        button(row,'CSV EXPORT',self.save_csv).pack(side='right',padx=2)
        self.progress=ttk.Progressbar(self,mode='determinate',maximum=100)
        self.progress.pack(fill='x',padx=8,pady=(3,0))
        cols=[('score','PRIO'),('status','STATUS'),('category','KATEGORIE'),('kind','TYP'),('class_context','KLASSE'),('file','DATEI'),('line','ZEILE'),('symbol','TREFFER / SIGNATUR')]
        self.tbl=ttk.Treeview(self,columns=[x[0] for x in cols],show='headings',height=19)
        for key,title in cols:self.tbl.heading(key,text=title);self.tbl.column(key,width={'score':50,'status':175,'category':185,'kind':145,'class_context':190,'file':230,'line':55,'symbol':430}[key],anchor='w')
        self.tbl.pack(fill='both',expand=True,padx=8,pady=8)
        bottom=tk.Label(self,bg=BG_CARD,fg=TEXT_DIM,justify='left',anchor='w',wraplength=1150,
          text='Erkennt Kandidaten für Gesundheit/Survival, Geld, Waffen/Munition, Inventar/Items, Bewegung, Debug-/Cheat-Menüs, Progress/Unlocks, Welt/AI, Fahrzeuge und sonstige Systeme. Reine Bau-/Herstellungskosten werden herausgefiltert. Treffer sind statische Hinweise, keine bestätigten Cheats.')
        bottom.pack(fill='x',padx=8,pady=(0,8),ipady=5)

    def pick_folder(self):
        p=filedialog.askdirectory(title='Unreal Dump / SDK-Ordner auswählen')
        if p:self.path.set(p)
    def pick_zip(self):
        p=filedialog.askopenfilename(title='Dump-/SDK-ZIP auswählen',filetypes=[('ZIP','*.zip'),('Alle Dateien','*.*')])
        if p:self.path.set(p)
    def scan(self):
        p=self.path.get().strip()
        if not p:return messagebox.showinfo('Universal Analyzer','Bitte zuerst Ordner oder ZIP auswählen.')
        if self.scanning:return
        self.scanning=True; self.cancel_event=threading.Event(); self.status.set('Scan läuft bzw. setzt vorhandenen Checkpoint fort …')
        self.progress['value']=0
        for x in self.tbl.get_children():self.tbl.delete(x)
        def progress(done,total,current):
            pct=(done/total*100) if total else 0
            self.after(0,lambda d=done,t=total,f=current,v=pct:self._progress(d,t,f,v))
        def job():
            try:r=analyze_dump(p,progress_callback=progress,cancel_event=self.cancel_event,resume=True); err=None
            except Exception as e:r=None;err=str(e)
            self.after(0,lambda:self._finish(r,err))
        threading.Thread(target=job,daemon=True).start()
    def _progress(self,done,total,current,pct):
        self.progress['value']=pct
        self.status.set(f'Scan: {done}/{total} Dateien ({pct:.1f} %) — {os.path.basename(current)}')
    def cancel_scan(self):
        if self.cancel_event and self.scanning:
            self.cancel_event.set(); self.status.set('Abbruch angefordert — Checkpoint wird gespeichert …')
    def restart_scan(self):
        if self.scanning:return messagebox.showinfo('Scan','Bitte laufenden Scan erst abbrechen.')
        p=self.path.get().strip()
        if not p:return messagebox.showinfo('Scan','Bitte zuerst Ordner oder ZIP auswählen.')
        if not messagebox.askyesno('Neu scannen','Vorhandenen Checkpoint für diese Quelle löschen und von vorn beginnen?'):return
        try:
            cp=default_checkpoint_path(p)
            if os.path.exists(cp):os.remove(cp)
            self.status.set('Checkpoint gelöscht. Nächster Scan startet von vorn.')
            self.progress['value']=0
        except Exception as e:messagebox.showerror('Checkpoint',str(e))
    def _finish(self,r,err):
        self.scanning=False
        if err:self.status.set('Fehler: '+err);return
        self.report=r
        for h in r['candidates'][:5000]:
            self.tbl.insert('', 'end', values=(h['score'],h.get('status','candidate'),h['category'],h['kind'],h.get('class_context') or '—',h['file'],h['line'],h['symbol']))
        if r.get('partial'):
            self.status.set(f"Teilscan gespeichert: {r['files_scanned']}/{r.get('total_files', '?')} Dateien | {r['candidate_count']} Treffer — SCAN / FORTSETZEN setzt fort.")
            return
        self.progress['value']=100
        self.status.set(f"Fertig: {r['files_scanned']} Dateien | {r['class_struct_lines']} Klassen-/Struct-Zeilen | {r['function_like_lines']} Funktionskandidaten | {r['candidate_count']} Treffer | {len(r.get('class_summary', []))} Klassenprofile (Anzeige max. 5.000).")
    def save_json(self):
        if not self.report:return messagebox.showinfo('Export','Bitte zuerst scannen.')
        p=filedialog.asksaveasfilename(defaultextension='.json',filetypes=[('JSON','*.json')])
        if p:
            try:export_report(self.report,p);messagebox.showinfo('Export','JSON-Bericht gespeichert.')
            except Exception as e:messagebox.showerror('Export',str(e))
    def save_csv(self):
        if not self.report:return messagebox.showinfo('Export','Bitte zuerst scannen.')
        p=filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('CSV','*.csv')])
        if p:
            try:export_csv(self.report,p);messagebox.showinfo('Export','CSV-Bericht gespeichert.')
            except Exception as e:messagebox.showerror('Export',str(e))
