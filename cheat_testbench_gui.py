#!/usr/bin/env python3
"""Small local GUI for marking static candidates as tested; never runs a cheat."""
import json, tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
class App:
 def __init__(self,root,path):
  self.root=root; self.path=Path(path); self.data=json.loads(self.path.read_text(encoding='utf8')); self.rows=self.data['candidates']; self.filtered=[]
  root.title('ReaperPy — Cheat Testbench (manual validation)'); root.geometry('1180x760')
  top=ttk.Frame(root,padding=8); top.pack(fill='x')
  self.game=tk.StringVar(value='All games'); self.cat=tk.StringVar(value='All categories'); self.status=tk.StringVar(value='All statuses'); self.search=tk.StringVar()
  ttk.Label(top,text='Game').pack(side='left'); ttk.Combobox(top,textvariable=self.game,state='readonly',values=['All games']+sorted({r['game'] for r in self.rows}),width=28).pack(side='left',padx=4)
  ttk.Label(top,text='Category').pack(side='left'); ttk.Combobox(top,textvariable=self.cat,state='readonly',values=['All categories']+sorted({r['category'] for r in self.rows}),width=27).pack(side='left',padx=4)
  ttk.Label(top,text='Status').pack(side='left'); ttk.Combobox(top,textvariable=self.status,state='readonly',values=['All statuses','NOT TESTED','PASS','FAIL','INCONCLUSIVE'],width=15).pack(side='left',padx=4)
  ttk.Label(top,text='Search').pack(side='left'); ttk.Entry(top,textvariable=self.search,width=22).pack(side='left',padx=4)
  for v in (self.game,self.cat,self.status,self.search): v.trace_add('write',lambda *_:self.refresh())
  body=ttk.Panedwindow(root,orient='horizontal'); body.pack(fill='both',expand=True,padx=8,pady=4)
  left=ttk.Frame(body); right=ttk.Frame(body,padding=8); body.add(left,weight=3); body.add(right,weight=2)
  self.tree=ttk.Treeview(left,columns=('game','category','confidence','status'),show='headings',selectmode='browse')
  for col,width in [('game',170),('category',190),('confidence',80),('status',110)]: self.tree.heading(col,text=col.title()); self.tree.column(col,width=width,stretch=True)
  ys=ttk.Scrollbar(left,orient='vertical',command=self.tree.yview); self.tree.configure(yscrollcommand=ys.set); self.tree.pack(side='left',fill='both',expand=True); ys.pack(side='right',fill='y'); self.tree.bind('<<TreeviewSelect>>',self.select)
  self.title=ttk.Label(right,text='Select a candidate',font=('TkDefaultFont',12,'bold'),wraplength=430); self.title.pack(anchor='w')
  self.evidence=tk.Text(right,height=13,wrap='word'); self.evidence.pack(fill='both',expand=True,pady=6)
  ttk.Label(right,text='Test status').pack(anchor='w'); self.result=tk.StringVar(value='NOT TESTED'); ttk.Combobox(right,textvariable=self.result,state='readonly',values=['NOT TESTED','PASS','FAIL','INCONCLUSIVE']).pack(fill='x')
  ttk.Label(right,text='Observed result / notes').pack(anchor='w',pady=(8,0)); self.notes=tk.Text(right,height=7,wrap='word'); self.notes.pack(fill='x')
  buttons=ttk.Frame(right); buttons.pack(fill='x',pady=8); ttk.Button(buttons,text='Save result',command=self.save).pack(side='left'); ttk.Button(buttons,text='Export updated JSON…',command=self.export).pack(side='left',padx=8)
  self.current=None; self.refresh()
 def refresh(self):
  for x in self.tree.get_children(): self.tree.delete(x)
  self.filtered=[]; term=self.search.get().lower()
  for i,r in enumerate(self.rows):
   if self.game.get()!='All games' and r['game']!=self.game.get(): continue
   if self.cat.get()!='All categories' and r['category']!=self.cat.get(): continue
   if self.status.get()!='All statuses' and r.get('test_status')!=self.status.get(): continue
   if term and term not in (r['symbol']+' '+r['category']+' '+r['game']).lower(): continue
   self.filtered.append(i); self.tree.insert('', 'end', iid=str(i),values=(r['game'],r['category'],r['confidence'],r.get('test_status','NOT TESTED')))
 def select(self,event=None):
  sel=self.tree.selection()
  if not sel:return
  self.current=int(sel[0]); r=self.rows[self.current]; self.title.config(text=r['symbol'])
  self.evidence.delete('1.0','end'); self.evidence.insert('end',f"Game: {r['game']}\nCategory: {r['category']}\nConfidence: {r['confidence']} (static heuristic)\nSource: {r['source_member']}:{r['gobjects_line']}\n\nEvidence:\n{r['raw_line']}\n\nTest protocol:\n{r['test_protocol']}\n\nWARNING: GObjects symbol metadata is not an executable address and does not prove the candidate works.")
  self.result.set(r.get('test_status','NOT TESTED')); self.notes.delete('1.0','end'); self.notes.insert('end',r.get('notes','') or r.get('test_result',''))
 def save(self):
  if self.current is None:return
  r=self.rows[self.current]; r['test_status']=self.result.get(); r['test_result']=self.notes.get('1.0','end').strip(); r['notes']=r['test_result']; self.data['last_saved_local']='manual'; self.path.write_text(json.dumps(self.data,indent=2,ensure_ascii=False),encoding='utf8'); self.refresh(); self.tree.selection_set(str(self.current)); messagebox.showinfo('Saved','Test status saved to the JSON catalog.')
 def export(self):
  fn=filedialog.asksaveasfilename(defaultextension='.json',filetypes=[('JSON','*.json')],initialfile='cheat_candidates_tested.json')
  if fn: Path(fn).write_text(json.dumps(self.data,indent=2,ensure_ascii=False),encoding='utf8'); messagebox.showinfo('Exported',fn)
if __name__=='__main__':
 import sys
 p=sys.argv[1] if len(sys.argv)>1 else 'cheat_testbench/cheat_candidates.json'
 root=tk.Tk(); App(root,p); root.mainloop()
