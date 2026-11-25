import unittest
from finalize_evaluation import verify_identity
class Tests(unittest.TestCase):
 def test_plan_key_does_not_allow_swapped_subgroup_labels(self):
  item=dict(split='testing',condition='clean__floor-60',row=dict(id=1,kind='positive',phrase='ehi_nira_it',variant='joined_ei',family='serena-fast-ehi_nira_it-joined_ei',duration=.8))
  row=dict(split='testing',condition='clean__floor-60',id=1,kind='positive',phrase='ehi_nira_it',variant='joined_ei',voice='serena',duration=5.8)
  verify_identity(row,item)
  for field,value in [('condition','off_axis_strong__floor-60'),('variant','pause'),('voice','paola'),('id',2),('split','validation'),('duration',4.8)]:
   with self.subTest(field=field):
    changed={**row,field:value}
    with self.assertRaises(AssertionError):verify_identity(changed,item)
if __name__=='__main__':unittest.main()
