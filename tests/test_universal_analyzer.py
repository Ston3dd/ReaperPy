import os, tempfile, unittest, zipfile
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from universal_analyzer import analyze_dump
class UniversalAnalyzerTests(unittest.TestCase):
 def test_scan_folder_and_filter_build_cost(self):
  with tempfile.TemporaryDirectory() as d:
   os.makedirs(os.path.join(d,'SDK_HEADERS'))
   p=os.path.join(d,'SDK_HEADERS','Player_classes.hpp')
   open(p,'w').write('class UPlayerInventory : public UObject {\n int32 Health;\n void GiveItem(FName ItemId, int32 Count);\n int32 BuildingMaterialCost;\n void OpenDebugMenu();\n};')
   r=analyze_dump(d)
   cats=' '.join(x['category'] for x in r['candidates'])
   syms=' '.join(x['symbol'] for x in r['candidates'])
   self.assertIn('Inventory / Items',cats);self.assertIn('Health / Survival',cats);self.assertIn('Debug / Cheat Menu',cats)
   self.assertNotIn('BuildingMaterialCost',syms)
 def test_scan_zip(self):
  with tempfile.TemporaryDirectory() as d:
   z=os.path.join(d,'a.zip')
   with zipfile.ZipFile(z,'w') as f:f.writestr('SDK/foo.hpp','void SetMoney(int32 Amount);')
   r=analyze_dump(z);self.assertGreater(r['candidate_count'],0)
 def test_checkpoint_resume(self):
  import threading
  with tempfile.TemporaryDirectory() as d:
   src=os.path.join(d,'src'); os.makedirs(src)
   for i in range(4):
    with open(os.path.join(src,f'{i}.hpp'),'w') as f:f.write(f'void SetMoney{i}(int32 Amount);\n')
   cp=os.path.join(d,'checkpoint.json'); ev=threading.Event()
   def progress(done,total,current):
    if done==1: ev.set()
   partial=analyze_dump(src,progress_callback=progress,cancel_event=ev,checkpoint_path=cp)
   self.assertTrue(partial.get('partial'))
   self.assertTrue(os.path.exists(cp))
   full=analyze_dump(src,checkpoint_path=cp,resume=True)
   self.assertFalse(full.get('partial',False))
   self.assertEqual(full['files_scanned'],4)
   self.assertGreaterEqual(full['candidate_count'],4)
   self.assertFalse(os.path.exists(cp))

 def test_profiles_and_item_catalog_are_reported(self):
  with tempfile.TemporaryDirectory() as d:
   os.makedirs(os.path.join(d,'SDK_HEADERS'))
   p=os.path.join(d,'SDK_HEADERS','Inventory_classes.hpp')
   with open(p,'w') as f:
    f.write('class UItemDefinition : public UObject {\n int32 ItemQuantity;\n void GiveItem(FName ItemId, int32 Count);\n};\nclass UBuildingRecipe : public UObject {\n int32 BuildingMaterialCost;\n};')
   r=analyze_dump(d)
   self.assertIn('capability_profiles',r)
   self.assertIn('item_catalog',r)
   self.assertTrue(any(x['class_name']=='UItemDefinition' for x in r['capability_profiles']))
   self.assertTrue(any(x['class_or_symbol']=='UItemDefinition' for x in r['item_catalog']))


 def test_zip_skips_identical_payload_duplicates(self):
  with tempfile.TemporaryDirectory() as d:
   z=os.path.join(d,'duplicate.zip')
   with zipfile.ZipFile(z,'w') as f:
    f.writestr('a.hpp','void SetMoney(int32 Amount);')
    f.writestr('nested/a_copy.hpp','void SetMoney(int32 Amount);')
   r=analyze_dump(z,checkpoint_path=os.path.join(d,'cp.json'),resume=False)
   self.assertEqual(r['files_scanned'],1)
   self.assertEqual(r['total_files'],1)

 def test_resume_rebuilds_capability_summary(self):
  import threading
  with tempfile.TemporaryDirectory() as d:
   src=os.path.join(d,'src'); os.makedirs(src)
   for i in range(3):
    with open(os.path.join(src,f'{i}.hpp'),'w') as f:f.write(f'class UPlayer{i} {{ int32 Health; void SetMoney(int32 Amount); }};')
   cp=os.path.join(d,'checkpoint.json'); ev=threading.Event()
   def progress(done,total,current):
    if done==1: ev.set()
   partial=analyze_dump(src,progress_callback=progress,cancel_event=ev,checkpoint_path=cp,resume=False)
   self.assertTrue(partial['partial'])
   resumed=analyze_dump(src,checkpoint_path=cp,resume=True)
   self.assertEqual(resumed['capability_summary'].get('Health / Survival',0),sum(1 for h in resumed['candidates'] if 'Health / Survival' in h['category']))

if __name__=='__main__':unittest.main()
