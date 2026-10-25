#!/usr/bin/env python3
"""ReaperPy Cheat Testbench — evidence-backed candidate catalog, manual validation tracker.
Static symbol discovery only. It does not invoke game functions or patch memory.
"""
from __future__ import annotations
import argparse,csv,json,re,zipfile
from pathlib import Path
from datetime import datetime

RULES=[
 ('AI / perception',r'HidePlayerFromAIPerception|IsCheatHiddenFromAIPerception|EnemyPlayerPerception|EnableSightDetection|ResetSightDetection|GetPlayerVisibleState|GetPlayerPerceptionProgress|SetBasePerceptionIncreaseRate|SetPeripheralVisionAngle|SetTimesBeforePerceptionIncrease|ForgetAllPerceptionStimuli|SetSightSenseDistances|SetSightSenseVisionAngle|SetHearingSenseRange|SetAlertState|GetAlertState|OnEnemyProximity'),
 ('Enemy spawn / freeze leads',r'SpawnEnemy|RespawnEnemy|DestroyEnemy|IsEnemySpawnPending|IsControlledBySpawnDirector|StopMovementImmediately|StopMovement|SetMovementMode|SetActorTickEnabled|SetActorHiddenInGame|TimeStop'),
 ('Health / survival',r'Health|\bHP\b|SetHP|Heal|Revive|Invulnerab|GodMode|Damage|Stamina|Hunger|Thirst|Oxygen'),
 ('Money / economy',r'Debug_AddMoney|AddMoney|SetMoney|MoneyData|Currency|Gold|Coin|Wallet|Balance'),
 ('Items / inventory',r'RequestAddItem|AddItem|GiveItem|GrantItem|CreateItem|Debug_CreateItemId|Inventory|ItemDefinition|StaticItemId|ItemId|Pickup|DropItem|ItemStack'),
 ('Weapons / ammo / combat',r'Ammo|Ammunition|Reload|Magazine|Weapon|Projectile|FireRate|Recoil|Attack|Damage'),
 ('Movement / traversal',r'Movement|WalkSpeed|RunSpeed|MoveSpeed|Jump|Fly|Teleport|Gravity|Sprint|NoClip|TimeDilation'),
 ('Debug / cheats / unlocks',r'Cheat|Debug|Developer|Console|Exec|Unlock|GiveAll|ToggleAllDebug|Open.*Menu|GodMode|NoClip|Invulnerab'),
 ('Progress / world',r'AddExperience|GiveExperience|SetExperience|AddXP|GiveXP|SetLevel|Unlock|SkillPoint|ResetSkill|DropRate|SetTimeOfDay|SetWeather|SetCooldown|CarryCapacity|WeightLimit'),
]
BUILD_ONLY=re.compile(r'(?:build(?:ing)?|construction|craft(?:ing)?|recipe|material|resource)[_ ]?(?:material[_ ]?)?cost|cost[_ ]?(?:of[_ ]?)?(?:building|construction|crafting|recipe|material)',re.I)
FUNCTION_LINE=re.compile(r'\b(?:Function|DelegateFunction)\s+(.+)$')
ACTION_SIGNAL=re.compile(r'add|give|grant|set|spawn|unlock|teleport|heal|revive|invulnerab|god.?mode|noclip|debug|cheat|exec|toggle|enable|disable|reset|restore|refill|increase|decrease|stopmovement|forgetall|hideplayer|setalertstate|setsightsense|sethearingsense|setbaseperception|setperipheralvision|settimesbeforeperception|setmovementmode|setactortick|time.?stop|requestadditem|createitem|destroyenemy|respawnenemy',re.I)

def load_gobjects(z, member):
    text=z.read(member).decode('utf-8','replace')
    return text.splitlines()

def game_name(member,archive):
    """Game label for a GObjects.txt member: its top-level folder inside the ZIP, else the ZIP's file name."""
    parts=[p for p in member.replace('\\','/').split('/') if p]
    return parts[0] if len(parts)>1 else Path(str(archive)).stem

def build(archive):
    rows=[]
    with zipfile.ZipFile(archive) as z:
        members=[n for n in z.namelist() if n.lower().endswith('gobjects.txt')]
        for member in members:
            game=game_name(member,archive)
            for line_no,line in enumerate(load_gobjects(z,member),1):
                if BUILD_ONLY.search(line): continue
                m=FUNCTION_LINE.search(line)
                if not m: continue
                symbol=m.group(1).strip()
                if not ACTION_SIGNAL.search(symbol): continue
                for category,pattern in RULES:
                    if re.search(pattern,symbol,re.I):
                        # Named game-specific evidence gets higher confidence; generic matches stay lower.
                        confidence='high' if any(x in symbol.lower() for x in ['_cheat','debug_addmoney','requestadditem_fordebug','hideplayerfromaiperception','ischeathiddenfromaiperception']) else ('medium' if any(x in symbol.lower() for x in ['additem','addmoney','setalertstate','spawnenemy','setsightsensedistances','sethp']) else 'low')
                        test = {
                         'AI / perception':'In a repeatable encounter, record detection before/after the candidate is independently enabled; separately test sight, hearing, scripted triggers, reload and newly spawned enemies.',
                         'Enemy spawn / freeze leads':'Observe an enemy from spawn through patrol, alert, attack and respawn. Record whether only movement stops or AI/tick/attacks also stop; test newly spawned enemies separately.',
                         'Health / survival':'Record health and damage source before/after a controlled hit; test healing, damage, death/revive and save/reload independently.',
                         'Money / economy':'Record balance, perform a small controlled transaction, then compare balance and persistence after save/reload.',
                         'Items / inventory':'Test one known item ID and count; verify inventory, stack limits, equip/use/drop, save/reload and multiplayer/server authority if applicable.',
                         'Weapons / ammo / combat':'Record weapon, magazine and reserve ammo; test firing, reload, swap, reload after save/load and damage separately.',
                         'Movement / traversal':'Measure baseline speed/jump/gravity; test movement, collision, falling, animation, reset and save/load separately.',
                         'Debug / cheats / unlocks':'Check whether the symbol is a menu/debug hook or only metadata; verify unlock/state persistence and avoid assuming symbol address is executable code.',
                         'Progress / world':'Record baseline value/state, change one variable, verify UI/world behavior and persistence independently.'
                        }[category]
                        rows.append({'game':game,'category':category,'confidence':confidence,'symbol':symbol,'source_member':member,'gobjects_line':line_no,'raw_line':line.strip(),'static_status':'candidate_only_not_runtime_validated','test_status':'NOT TESTED','test_result':'','notes':'','test_protocol':test})
                        break
    # de-duplicate symbols within game/category while preserving source evidence
    seen=set(); out=[]
    for r in rows:
        k=(r['game'],r['category'],r['symbol'])
        if k not in seen: seen.add(k); out.append(r)
    return sorted(out,key=lambda r:({'high':0,'medium':1,'low':2}[r['confidence']],r['game'],r['category'],r['symbol'].lower()))

def main():
    p=argparse.ArgumentParser(description='Build static cheat-candidate test catalog from a dumper ZIP')
    p.add_argument('archive',help='Dump ZIP containing GObjects.txt')
    p.add_argument('--out',default='cheat_testbench')
    a=p.parse_args(); out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    rows=build(a.archive)
    (out/'cheat_candidates.json').write_text(json.dumps({'generated_at':datetime.now().isoformat(timespec='seconds'),'source_archive':str(Path(a.archive).name),'mode':'static evidence only; no game memory writes or function calls','candidate_count':len(rows),'candidates':rows},indent=2,ensure_ascii=False),encoding='utf-8')
    with (out/'cheat_test_matrix.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys()) if rows else ['game','category','symbol']); w.writeheader(); w.writerows(rows)
    print(f'Candidates: {len(rows)}')
    for game in sorted({r['game'] for r in rows}):
        sub=[r for r in rows if r['game']==game]
        print(f'{game}: {len(sub)}')
        for cat in sorted({r['category'] for r in sub}): print(f'  {cat}: {sum(r["category"]==cat for r in sub)}')
if __name__=='__main__': main()
