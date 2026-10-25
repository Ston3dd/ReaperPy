"""Evidence-based Unreal capability and item-definition profile builder.

This module intentionally performs static classification only. It does not modify game memory.
"""
from __future__ import annotations
import re
from collections import defaultdict

CAPABILITY_RULES = {
    'health_survival': (r'health|\bhp\b|stamina|hunger|thirst|oxygen|breath|survival|invulnerab|god.?mode|heal|revive', r'health|stamina|hunger|thirst|oxygen|damage|heal|revive|god'),
    'currency_economy': (r'money|currency|gold|coin|cash|credit|wallet|bank|funds|economy|price', r'money|currency|gold|coin|cash|credit|wallet|balance|funds|economy'),
    'weapons_ammo': (r'weapon|firearm|ammo|ammunition|bullet|magazine|reload|projectile|recoil|fire.?rate', r'weapon|ammo|bullet|magazine|reload|projectile|attack|damage'),
    'inventory_items': (r'inventory|item|slot|backpack|container|quick.?bar|loot|pickup|stack|FName|FString|FText', r'item|inventory|slot|container|loot|pickup|stack|give|grant|add'),
    'debug_console': (r'debug|cheat|console|developer|admin|exec|test.?menu|cheatmanager', r'debug|cheat|console|developer|admin|exec|menu|command'),
    'movement_traversal': (r'movement|walk.?speed|run.?speed|jump|fly|teleport|gravity|sprint|noclip|playerpawn', r'move|speed|jump|fly|teleport|gravity|sprint|noclip'),
    'progress_unlocks': (r'experience|\bxp\b|level|skill.?point|talent|perk|unlock|achievement|quest|mission|reputation', r'experience|level|skill|talent|perk|unlock|achievement|quest|mission'),
    'world_ai_spawn': (r'world|weather|time.?of.?day|spawn|npc|enemy|creature|ai.?controller|loot.?table', r'world|weather|time|spawn|npc|enemy|creature|ai|loot'),
    'equipment_vehicles': (r'equipment|armor|armour|gear|durability|vehicle|mount|fuel|attachment', r'equipment|armor|gear|durability|vehicle|mount|fuel|attachment'),
    'save_settings_misc': (r'savegame|save.?game|profile|setting|cooldown|timer|weight|carry.?capacity|craft.?speed', r'save|profile|setting|cooldown|timer|weight|capacity'),
}
ITEM_CLASS = re.compile(r'(?:^|\b)(?:U|A|F)?(?:.*(?:Item|Inventory|Loot|Pickup|Equipment|Weapon|Consumable|ItemData|ItemDefinition|ItemSlot|ItemStack).*)$', re.I)
ITEM_NAME = re.compile(r'item|loot|pickup|inventory|slot|stack|equipment|weapon|consumable|itemdata|itemdefinition', re.I)
NOT_ITEM = re.compile(r'widget|blueprint.?library|recipe|craft|building|construction|material.?cost|build.?cost|quest.?objective|tooltip|icon|thumbnail|scrolllist|button|entry.?widget', re.I)
ACTION = re.compile(r'add|give|grant|spawn|create|insert|push|equip|pickup|drop|remove|consume|set|unlock|open|execute|cheat|debug|teleport|heal|revive|restore|refill', re.I)

def build_capability_profiles(hits):
    """Group evidence by class and infer possible capabilities without claiming validation."""
    grouped = defaultdict(lambda: {'evidence': [], 'categories': set(), 'files': set(), 'functions': [], 'properties': [], 'scores': []})
    for hit in hits:
        cls = hit.get('class_context')
        if not cls:
            continue
        row = grouped[cls]
        row['evidence'].append(hit)
        row['categories'].update(x.strip() for x in (hit.get('category') or '').split(';') if x.strip())
        if hit.get('file'): row['files'].add(hit['file'])
        if hit.get('kind') == 'Function candidate' and hit.get('function_signature'): row['functions'].append(hit['function_signature'])
        if hit.get('kind') == 'Property / data candidate': row['properties'].append(hit.get('symbol'))
        row['scores'].append(int(hit.get('score') or 0))
    profiles=[]
    for cls, row in grouped.items():
        joined = ' '.join([cls] + row['functions'] + row['properties'] + [h.get('evidence','') for h in row['evidence']]).lower()
        capabilities=[]
        for name,(class_pat,signal_pat) in CAPABILITY_RULES.items():
            if re.search(class_pat, cls, re.I) or re.search(signal_pat, joined, re.I):
                capabilities.append(name)
        actionable = [f for f in row['functions'] if ACTION.search(f)]
        profiles.append({'class_name':cls,'capabilities':capabilities,'evidence_count':len(row['evidence']),
          'function_candidates':list(dict.fromkeys(row['functions']))[:100],
          'action_like_functions':list(dict.fromkeys(actionable))[:50],
          'property_candidates':list(dict.fromkeys(x for x in row['properties'] if x))[:100],
          'source_files':sorted(row['files']),'max_static_score':max(row['scores'] or [0]),
          'validation_status':'unvalidated_static_profile'})
    return sorted(profiles,key=lambda p:(-len(p['action_like_functions']),-p['evidence_count'],p['class_name'].lower()))

def build_item_catalog(hits):
    """Rank item-definition and inventory plumbing candidates; separate UI/recipe noise."""
    groups=defaultdict(lambda:{'evidence':[],'functions':[],'properties':[],'files':set(),'score':0})
    for h in hits:
        cls=h.get('class_context') or h.get('symbol') or ''
        evidence=' '.join(str(h.get(k) or '') for k in ('class_context','symbol','evidence','function_signature','file'))
        if not ITEM_NAME.search(evidence): continue
        if NOT_ITEM.search(cls) or NOT_ITEM.search(h.get('file','')):
            classification='likely_ui_recipe_or_build_noise'
        elif re.search(r'itemdefinition|itemdata|iteminfo|itemconfig|itemtable|itemdatabase|itemcatalog', cls, re.I):
            classification='possible_item_definition'
        elif re.search(r'inventory|itemslot|itemstack|container|loot|pickup', cls, re.I):
            classification='inventory_or_item_flow'
        else:
            classification='item_related_unclassified'
        key=(cls,classification)
        g=groups[key];g['evidence'].append(h)
        if h.get('kind')=='Function candidate' and h.get('function_signature'):g['functions'].append(h['function_signature'])
        if h.get('kind')=='Property / data candidate' and h.get('symbol'):g['properties'].append(h['symbol'])
        if h.get('file'):g['files'].add(h['file'])
        g['score']=max(g['score'],int(h.get('score') or 0))
    result=[]
    for (cls,classification),g in groups.items():
        funcs=list(dict.fromkeys(g['functions']))
        can_add=any(re.search(r'add|give|grant|insert|create|pickup|spawn',f,re.I) for f in funcs)
        if classification=='possible_item_definition' and can_add: classification='item_definition_with_add_flow_signal'
        result.append({'class_or_symbol':cls,'classification':classification,'add_flow_signal':can_add,
          'evidence_count':len(g['evidence']),'function_candidates':funcs[:50],
          'property_candidates':list(dict.fromkeys(g['properties']))[:80],'source_files':sorted(g['files']),
          'max_static_score':g['score'],'validation_status':'unvalidated_static_candidate'})
    order={'item_definition_with_add_flow_signal':0,'possible_item_definition':1,'inventory_or_item_flow':2,'item_related_unclassified':3,'likely_ui_recipe_or_build_noise':4}
    return sorted(result,key=lambda x:(order.get(x['classification'],9),-x['evidence_count'],x['class_or_symbol'].lower()))
