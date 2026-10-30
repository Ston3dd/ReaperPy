"""Universal Unreal Engine SDK/dump analyzer. Read-only, evidence-backed static discovery."""
from __future__ import annotations
import csv, json, re, zipfile, hashlib, time
from unreal_profiles import build_capability_profiles, build_item_catalog
from pathlib import Path

RULES = {
 'Health / Survival': [r'health',r'\bhp\b',r'stamina',r'energy',r'hunger',r'thirst',r'oxygen',r'breath',r'survival',r'damage',r'heal',r'revive',r'god.?mode',r'invulnerab',r'poison',r'bleed'],
 'Money / Economy': [r'currency',r'money',r'gold',r'coin',r'cash',r'credit',r'wallet',r'funds',r'premium',r'\bcurrency\b',r'setmoney',r'addmoney',r'givegold',r'bankbalance'],
 'Weapons / Combat': [r'weapon',r'firearm',r'\bgun\b',r'ammo',r'ammunition',r'bullet',r'reload',r'attack',r'damage',r'critical',r'projectile',r'aim',r'recoil',r'fire.?rate',r'magazine'],
 'Inventory / Items': [r'inventory',r'item',r'pickup',r'loot',r'itemslot',r'item_slot',r'additem',r'giveitem',r'grantitem',r'consume',r'quantity',r'stack',r'container',r'quick.?bar',r'backpack',r'FName',r'FString',r'FText'],
 'Character / Movement': [r'playercharacter',r'player.?pawn',r'movement',r'walk.?speed',r'run.?speed',r'move.?speed',r'jump',r'fly',r'teleport',r'gravity',r'crouch',r'sprint',r'playercontroller',r'no.?clip'],
 'Debug / Cheat Menu': [r'debug',r'cheat',r'console',r'\bexec\b',r'godmode',r'dev.?menu',r'developer',r'admin',r'test.?menu',r'spawn',r'give.?all',r'unlock.?all',r'cheatmanager',r'debugmenu'],
 'Progress / Unlocks': [r'experience',r'\bexp\b',r'level',r'\bxp\b',r'skill.?point',r'talent',r'perk',r'unlock',r'achievement',r'quest',r'mission',r'reputation',r'affinity',r'progression'],
 'World / AI / Spawning': [r'worldstate',r'time.?of.?day',r'weather',r'spawn',r'npc',r'ai.?controller',r'enemy',r'creature',r'loot.?table',r'drop.?rate',r'world.?event',r'time.?scale'],
 'Vehicles / Equipment': [r'vehicle',r'mount',r'armor',r'armour',r'equipment',r'gear',r'durability',r'fuel',r'engine',r'attachment'],
 'Save / Settings / Misc': [r'savegame',r'save.?game',r'profile',r'option',r'setting',r'cooldown',r'timer',r'weight',r'carry.?capacity',r'weight.?limit',r'cooldown',r'craft.?speed'],
 'Crafting / Build (reference only)': [r'craft',r'recipe',r'building',r'construction',r'material.?cost',r'build.?cost']
}
RULE_RE={k:re.compile('|'.join('(?:'+x+')' for x in v),re.I) for k,v in RULES.items()}
# Filter only lines whose subject is a construction/crafting cost; don't discard mixed inventory/debug functions.
BUILD_ONLY=re.compile(r'(?:build(?:ing)?|construction|craft(?:ing)?|recipe|material|resource)[_ ]?(?:material[_ ]?)?cost|cost[_ ]?(?:of[_ ]?)?(?:building|construction|crafting|recipe|material)',re.I)
ACTION=re.compile(r'\b(?:add|give|grant|set|spawn|unlock|teleport|heal|revive|debug|cheat|exec|reset|restore|refill|increase|decrease|god|noclip|openmenu|open.?debug)\w*\b',re.I)
FAST_GATE=re.compile(r'health|\bhp\b|stamina|energy|hunger|thirst|oxygen|damage|heal|revive|god|invulnerab|currency|money|gold|coin|cash|credit|wallet|funds|weapon|ammo|bullet|reload|attack|projectile|recoil|inventory|item|pickup|loot|additem|giveitem|grantitem|consume|quantity|stack|container|backpack|playercharacter|playerpawn|movement|speed|jump|fly|teleport|gravity|sprint|debug|cheat|console|developer|admin|spawn|unlock|experience|level|skill|talent|perk|achievement|quest|mission|reputation|craft|recipe|building|construction|worldstate|weather|npc|enemy|creature|vehicle|mount|armor|armour|equipment|durability|fuel|savegame|profile|cooldown|timer|weight|fstring|fname|ftext|setmoney|addmoney|givegold|noclip|no.?clip',re.I)
CLASS=re.compile(r'\b(?:class|struct)\s+(\w+)(?:\s*:\s*(?:public\s+)?([\w:]+))?')
FUNC=re.compile(r'\b(?:virtual\s+|static\s+|inline\s+)*(?:[\w:<>,*&]+\s+)+([A-Za-z_]\w*)\s*\(([^;{}]*)\)\s*(?:const\s*)?;')
PROPERTY=re.compile(r'\b(?:UPROPERTY\s*\([^)]*\)\s*)?([\w:<>*&]+)\s+([A-Za-z_]\w*)\s*(?:=[^;]*)?;')
EXTS={'.hpp','.h','.txt','.json','.ini','.usmap','.csv'}
# Dumper exports such as GObjects.txt can exceed 25 MB; include them but cap pathological inputs.
MAX_SOURCE_BYTES=128_000_000
FAST_TERMS=tuple(x.lower() for x in ('health','stamina','hunger','thirst','oxygen','damage','heal','revive','god','invulnerab','currency','money','gold','coin','cash','credit','wallet','funds','weapon','ammo','bullet','reload','attack','projectile','recoil','inventory','item','pickup','loot','additem','giveitem','grantitem','consume','quantity','stack','container','backpack','playercharacter','playerpawn','movement','speed','jump','fly','teleport','gravity','sprint','debug','cheat','console','developer','admin','spawn','unlock','experience','level','skill','talent','perk','achievement','quest','mission','reputation','craft','recipe','building','construction','worldstate','weather','npc','enemy','creature','vehicle','mount','armor','armour','equipment','durability','fuel','savegame','profile','cooldown','timer','weight','fstring','fname','ftext','setmoney','addmoney','givegold','noclip','no-clip'))

def _iter_sources(path, start_after=None):
 """Yield supported source files lazily; resume skips reading prior files."""
 p=Path(path)
 if p.is_dir():
  files=sorted((f for f in p.rglob('*') if f.is_file() and f.suffix.lower() in EXTS), key=lambda x:(x.suffix.lower()=='.txt',str(x.relative_to(p)).lower()))
  passed = start_after is None
  for f in files:
   rel=str(f.relative_to(p))
   if not passed:
    if rel == start_after: passed=True
    continue
   try:
    if f.stat().st_size<=MAX_SOURCE_BYTES: yield rel,f.read_text(encoding='utf-8',errors='ignore')
   except OSError: pass
 elif p.is_file() and zipfile.is_zipfile(p):
  with zipfile.ZipFile(p) as z:
   infos=sorted((i for i in z.infolist() if not i.is_dir() and Path(i.filename).suffix.lower() in EXTS and i.file_size<=MAX_SOURCE_BYTES), key=lambda i:(Path(i.filename).suffix.lower()=='.txt',i.filename.lower()))
   passed = start_after is None
   seen_payloads=set()
   for info in infos:
    n=info.filename
    # Dumper bundles commonly repeat the exact same GObjects/header export at multiple paths.
    # CRC + uncompressed size lets us skip identical payloads without decompressing them again.
    fingerprint=(info.CRC,info.file_size)
    if fingerprint in seen_payloads:
     if not passed and n==start_after: passed=True
     continue
    seen_payloads.add(fingerprint)
    if not passed:
     if n == start_after: passed=True
     continue
    try: yield n,z.read(info).decode('utf-8','ignore')
    except (KeyError,OSError,RuntimeError): pass

def _count_sources(path):
 p=Path(path)
 if p.is_dir():
  return sum(1 for f in p.rglob('*') if f.is_file() and f.suffix.lower() in EXTS and _size_ok(f))
 if p.is_file() and zipfile.is_zipfile(p):
  with zipfile.ZipFile(p) as z:
   fingerprints={(i.CRC,i.file_size) for i in z.infolist() if not i.is_dir() and Path(i.filename).suffix.lower() in EXTS and i.file_size<=MAX_SOURCE_BYTES}
   return len(fingerprints)
 return 0

def _size_ok(path):
 try: return Path(path).stat().st_size<=MAX_SOURCE_BYTES
 except OSError: return False

def _source_signature(path):
 p=Path(path)
 if p.is_file():
  st=p.stat(); raw=f'{p.resolve()}|{st.st_size}|{st.st_mtime_ns}'
 else:
  parts=[]
  for f in sorted((x for x in p.rglob('*') if x.is_file() and x.suffix.lower() in EXTS),key=lambda x:str(x).lower()):
   try:
    st=f.stat(); parts.append(f'{f.relative_to(p)}:{st.st_size}:{st.st_mtime_ns}')
   except OSError: pass
  raw=f'{p.resolve()}|'+'|'.join(parts)
 return hashlib.sha256(raw.encode('utf-8','ignore')).hexdigest()

def default_checkpoint_path(path):
 key=hashlib.sha256(str(Path(path).resolve()).encode('utf-8','ignore')).hexdigest()[:20]
 root=Path.home()/'.reaperpy'/'unreal_scans'
 root.mkdir(parents=True,exist_ok=True)
 return str(root/(key+'.checkpoint.json'))

def _categories(text): return [k for k,rx in RULE_RE.items() if rx.search(text)]
def analyze_dump(path, progress_callback=None, cancel_event=None, checkpoint_path=None, resume=True):
 """Incremental read-only analysis. Checkpoints are saved after each source file.
 progress_callback(done, total, current_file) is optional. cancel_event may be threading.Event.
 """
 p=Path(path)
 if not p.exists(): raise FileNotFoundError(path)
 cp=Path(checkpoint_path or default_checkpoint_path(path))
 signature=_source_signature(path)
 total=_count_sources(p)
 hits=[]; files=class_lines=func_lines=0; metadata=[]; class_names=set(); capability_counts={}; last_file=None
 if resume and cp.exists():
  try:
   saved=json.loads(cp.read_text(encoding='utf-8'))
   if saved.get('source_signature')==signature:
    hits=saved.get('hits',[]); files=int(saved.get('files_scanned',0)); class_lines=int(saved.get('class_struct_lines',0)); func_lines=int(saved.get('function_like_lines',0)); metadata=saved.get('metadata_files',[]); last_file=saved.get('last_file')
  except (OSError,ValueError,TypeError): pass
 seen={(h.get('file'),h.get('line'),h.get('evidence')) for h in hits}
 for h in hits:
  for c in (h.get('category') or '').split('; '):
   if c: capability_counts[c]=capability_counts.get(c,0)+1
 def save_checkpoint(last):
  payload={'source_signature':signature,'last_file':last,'files_scanned':files,'class_struct_lines':class_lines,'function_like_lines':func_lines,'metadata_files':metadata,'hits':hits,'updated_at':time.time()}
  tmp=cp.with_suffix(cp.suffix+'.tmp')
  tmp.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8'); tmp.replace(cp)
 for rel,text in _iter_sources(p, start_after=last_file):
  files+=1; is_header=rel.lower().endswith(('.hpp','.h')); active_class=''; class_depth=0
  if rel.lower().endswith('.json') and any(k in rel.lower() for k in ('dump.bin.engine.json','offsets.json','dump.json')):
   try:
    obj=json.loads(text[:5_000_000]); metadata.append({'file':rel,'keys':list(obj.keys())[:50] if isinstance(obj,dict) else ['<root '+type(obj).__name__+'>']})
   except Exception: pass
  for lineno,line in enumerate(text.splitlines(),1):
   s=line.strip()
   if not s or s.startswith(('//','#include','#pragma')): continue
   cm=CLASS.search(s) if ('class ' in s.lower() or 'struct ' in s.lower()) else None
   if not cm and not (any(term in s.lower() for term in FAST_TERMS) if rel.lower().endswith('.txt') else FAST_GATE.search(s)):
    # Keep tracking braces for an open class, but avoid expensive category regex on irrelevant lines.
    if active_class:
     class_depth += s.count('{')-s.count('}')
     if class_depth<=0 and '}' in s: active_class=''
    continue
   if cm:
    active_class=cm.group(1); class_names.add(active_class); class_lines+=1; class_depth=s.count('{')-s.count('}')
   elif active_class: class_depth += s.count('{')-s.count('}')
   if active_class and class_depth<=0 and '}' in s: active_class=''
   fm=FUNC.search(s); pm=PROPERTY.search(s)
   if fm: func_lines+=1
   cats=_categories(s)
   if not cats and not cm: continue
   # Exclude construction/crafting price fields/functions unless the line also has a real non-cost capability.
   nonbuild=[c for c in cats if c!='Crafting / Build (reference only)']
   if BUILD_ONLY.search(s) and not (ACTION.search(s) and nonbuild): continue
   if not cats: cats=['Class / Struct']
   if cm: kind='Class / struct'; symbol=cm.group(1); active_class=cm.group(1)
   elif fm: kind='Function candidate'; symbol=fm.group(1)
   elif pm and any(x in s for x in ('UPROPERTY','FString','FName','FText','TArray','int32','float','bool','double','uint','int64')): kind='Property / data candidate'; symbol=pm.group(2)
   else: kind='Symbol / reference'; symbol=(fm.group(1) if fm else (pm.group(2) if pm else s[:120]))
   # Higher score requires an actionable verb and a meaningful typed method/property, not merely a keyword.
   score=2 + (2 if fm else 0) + (1 if is_header else 0) + (1 if ACTION.search(s) else 0) + (1 if active_class else 0)
   score=min(score,6)
   status='candidate'
   if score>=5 and fm and ACTION.search(s): status='high-priority static candidate'
   elif score>=4: status='structured candidate'
   else: status='weak reference'
   key=(rel,lineno,s)
   if key in seen: continue
   seen.add(key)
   hit={'score':score,'status':status,'category':'; '.join(cats),'kind':kind,'file':rel,'line':lineno,'class_context':active_class or None,'symbol':symbol,'evidence':s[:360], 'function_signature':s[:500] if fm else None,'base_class':cm.group(2) if cm else None}
   hits.append(hit)
   for c in cats: capability_counts[c]=capability_counts.get(c,0)+1
  last_file=rel
  if progress_callback:
   try: progress_callback(files, total, rel)
   except Exception: pass
  should_cancel = cancel_event is not None and cancel_event.is_set()
  if files % 25 == 0 or should_cancel:
   save_checkpoint(last_file)
  if should_cancel:
   return {'schema_version':3,'source':str(p),'files_scanned':files,'total_files':total,'class_struct_lines':class_lines,'function_like_lines':func_lines,'candidate_count':len(hits),'candidates':hits[:30000],'partial':True,'checkpoint_path':str(cp),'status_legend':{'high-priority static candidate':'action verb and function-like signature; still unvalidated','structured candidate':'typed property/function or class-associated reference; still unvalidated','weak reference':'name-only or generic symbol match'},'limitations':['Partial scan: resume the same source to continue.','Static SDK/dump analysis only; candidates are not validated cheats.']}
 if last_file: save_checkpoint(last_file)
 hits.sort(key=lambda h:(-h['score'],h['category'],h['file'],h['line']))
 # Summaries help the next-stage profile builder without pretending a hit is a working cheat.
 class_summary={}
 for h in hits:
  c=h.get('class_context')
  if c: class_summary.setdefault(c,{'candidate_count':0,'categories':set(),'functions':[],'files':set()}); class_summary[c]['candidate_count']+=1; class_summary[c]['categories'].update(h['category'].split('; ')); class_summary[c]['files'].add(h['file']);
  if c and h['kind']=='Function candidate' and len(class_summary[c]['functions'])<30: class_summary[c]['functions'].append(h['function_signature'])
 classes=[{'class':k,'candidate_count':v['candidate_count'],'categories':sorted(v['categories']),'files':sorted(v['files']),'function_candidates':v['functions']} for k,v in sorted(class_summary.items(),key=lambda x:-x[1]['candidate_count'])]
 report={'schema_version':3,'source':str(p),'files_scanned':files,'total_files':total,'partial':False,'checkpoint_path':str(cp),'class_struct_lines':class_lines,'function_like_lines':func_lines,'candidate_count':len(hits),'candidates':hits[:30000],'capability_summary':dict(sorted(capability_counts.items(),key=lambda x:-x[1])),'class_summary':classes[:5000],'capability_profiles':build_capability_profiles(hits)[:10000],'item_catalog':build_item_catalog(hits)[:10000],'metadata_files':metadata,'status_legend':{'high-priority static candidate':'action verb and function-like signature; still unvalidated','structured candidate':'typed property/function or class-associated reference; still unvalidated','weak reference':'name-only or generic symbol match'},'limitations':['Static SDK/dump analysis only; a candidate does not prove a callable function or writable field.','No live memory writes, runtime function calls, code patching, or automatic cheat activation.','Crafting/build-cost-only lines are filtered; unrelated crafting systems are not used as cheat candidates.','Class context is heuristic and may be imperfect for generated headers and one-line declarations.','A missing match does not prove a capability is absent; stripped symbols or runtime-only data may hide it.']}
 try: cp.unlink(missing_ok=True)
 except OSError: pass
 return report

def export_report(report,output_path): Path(output_path).write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
def export_csv(report,output_path):
 with open(output_path,'w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=['score','status','category','kind','class_context','file','line','symbol','function_signature','evidence']);w.writeheader()
  for h in report.get('candidates',[]): w.writerow({k:h.get(k) for k in w.fieldnames})
