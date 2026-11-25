import unittest,importlib.util
from pathlib import Path
p=Path(__file__).resolve().parents[2]/'homeassistant/custom_components/nyra_wake/audio_buffer.py'
s=importlib.util.spec_from_file_location('buffer_under_test',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_command_received_during_verification_is_preserved(self):
  b=m.AudioBuffer(seconds=4)
  for i in range(70):b.append(bytes([i])*3200,i*100)
  q=b.after(4800)
  self.assertEqual(q[0][1],4800);self.assertEqual(q[-1][1],6900)
  self.assertEqual(b''.join(x[0] for x in q),b''.join(bytes([i])*3200 for i in range(48,70)))
 def test_partial_chunk_trim_is_sample_aligned(self):
  b=m.AudioBuffer(seconds=4);b.append(bytes(3200),5000);q=b.after(5031)
  self.assertEqual(len(q[0][0]),2208);self.assertEqual(q[0][1],5031)
 def test_retention_and_reset(self):
  b=m.AudioBuffer(seconds=4)
  for i in range(200):b.append(bytes(640),i*20)
  self.assertLessEqual(b.byte_count,128000);b.append(bytes(640),4000);self.assertLessEqual(b.byte_count,128000)
  b.clear();self.assertEqual(b.after(0),[])
if __name__=='__main__':unittest.main()
