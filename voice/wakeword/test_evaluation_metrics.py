import unittest
from evaluate_candidate import report
class Tests(unittest.TestCase):
 def test_solo_nira_is_negative_control_including_preword_false_activation(self):
  row=dict(split='testing',kind='positive',phrase='nira_it',duration=6,hit=False,detections=[{'t':1.0}])
  metrics=report([row])['testing']
  self.assertEqual(metrics['solo_nira_hits'],1)
  self.assertEqual(metrics['solo_nira_total'],1)
  self.assertEqual(metrics['positive_total'],0)
if __name__=='__main__':unittest.main()
