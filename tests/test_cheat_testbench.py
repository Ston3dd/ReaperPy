import unittest,sys,zipfile,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent.parent))
from cheat_testbench import build
class Tests(unittest.TestCase):
 def test_build_filters_costs_and_finds_candidates(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.zip'
   with zipfile.ZipFile(p,'w') as z:z.writestr('GObjects.txt','[1] Function /Script/Pal.PalCheatManager.AddMoney\n[2] Function /Script/Townfall.TownfallPlayerCharacter.HidePlayerFromAIPerception_Cheat\n[3] Function /Script/Engine.Builder.BuildingMaterialCost')
   r=build(p); syms=[x['symbol'] for x in r]
   self.assertTrue(any('AddMoney' in x for x in syms)); self.assertTrue(any('HidePlayerFromAIPerception_Cheat' in x for x in syms)); self.assertFalse(any('BuildingMaterialCost' in x for x in syms))
 def test_rows_have_manual_validation_fields(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'a.zip'
   with zipfile.ZipFile(p,'w') as z:z.writestr('GObjects.txt','Function /Script/Pal.PalCheatManager.AddMoney')
   r=build(p)[0]; self.assertEqual(r['test_status'],'NOT TESTED'); self.assertIn('test_protocol',r)
if __name__=='__main__':unittest.main()
