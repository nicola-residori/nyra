import unittest,json
from pathlib import Path
from collections import deque
from candidate_engine import CandidateEngine
class Front:
 def process_streaming(self,b):yield None
class Head:
 def process_streaming(self,b):yield .9
class Vad:
 def probabilities(self,b):return [0.]
def engine(limit):
 e=CandidateEngine.__new__(CandidateEngine);e.config=json.loads((Path(__file__).parent/'model/config.json').read_text());e.front=Front();e.primary=Head();e.vad=Vad();e.session=None;e.samples=0;e.ring=bytearray();e.consecutive=0;e.last_candidate=-1e9;e.pending=deque();e.candidates=[];e.detections=[];e.history_limit=limit;return e
class Tests(unittest.TestCase):
 def test_continuous_rejected_candidates_have_bounded_service_history(self):
  bounded=engine(3);full=engine(None)
  for _ in range(1000):
   self.assertEqual(bounded.feed(bytes(2560)),full.feed(bytes(2560)))
  self.assertLessEqual(len(bounded.candidates),3)
  self.assertGreater(len(full.candidates),20)
  clean=lambda rows:[{k:v for k,v in r.items() if k!='verifier_wall_seconds'} for r in rows]
  self.assertEqual(clean(bounded.candidates),clean(full.candidates[-3:]))
if __name__=='__main__':unittest.main()
