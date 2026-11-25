import asyncio,unittest,importlib.util,sys,time
from unittest.mock import patch
from pathlib import Path
from wyoming.event import async_read_event,async_write_event
from wyoming.audio import AudioChunk,AudioStop
from wyoming.wake import Detection
root=Path(__file__).resolve().parents[2]/'homeassistant/custom_components';sys.path.insert(0,str(root));from nyra_wake.stream import detect_stream
from nyra_wake import stream as stream_module
class Tests(unittest.IsolatedAsyncioTestCase):
 async def test_real_socket_preserves_command_audio_received_before_delayed_detection(self):
  async def backend(reader,writer):
   n=0
   try:
    while e:=await async_read_event(reader):
     if AudioChunk.is_type(e.type):
      n+=1
      if n==70:
       await async_write_event(Detection(name='ehi_nira_it',timestamp=5400).event(),writer);break
   finally:writer.close();await writer.wait_closed()
  server=await asyncio.start_server(backend,'127.0.0.1',0)
  async def audio():
   for i in range(150):
    await asyncio.sleep(.002);yield bytes([i%256])*3200,i*100
  try:
   d,q=await detect_stream(audio(),'127.0.0.1',server.sockets[0].getsockname()[1],'ehi_nira_it')
   self.assertEqual(d.name,'ehi_nira_it');self.assertEqual(q[0][1],4400);self.assertGreaterEqual(q[-1][1],6900)
   self.assertEqual(q[0][0],bytes([44])*3200)
  finally:server.close();await server.wait_closed()
 async def test_backend_eof_cleans_up_even_when_microphone_stalls(self):
  async def backend(reader,writer):
   while e:=await async_read_event(reader):
    if AudioChunk.is_type(e.type):break
   writer.close();await writer.wait_closed()
  server=await asyncio.start_server(backend,'127.0.0.1',0)
  async def audio():
   yield bytes(3200),0
   await asyncio.Event().wait()
  try:
   result=await asyncio.wait_for(detect_stream(audio(),'127.0.0.1',server.sockets[0].getsockname()[1],'ehi_nira_it'),.5)
   self.assertEqual(result,(None,[]))
  finally:server.close();await server.wait_closed()
 async def test_finite_source_drains_pending_verification(self):
  async def backend(reader,writer):
   try:
    while e:=await async_read_event(reader):
     if AudioStop.is_type(e.type):
      await asyncio.sleep(.03);await async_write_event(Detection(name='ehi_nira_it',timestamp=200).event(),writer);break
   finally:writer.close();await writer.wait_closed()
  server=await asyncio.start_server(backend,'127.0.0.1',0)
  async def audio():
   for i in range(10):yield bytes([i])*3200,i*100
  try:
   d,q=await asyncio.wait_for(detect_stream(audio(),'127.0.0.1',server.sockets[0].getsockname()[1],'ehi_nira_it'),1)
   self.assertIsNotNone(d);self.assertEqual(q[-1][1],900)
  finally:server.close();await server.wait_closed()
 async def test_unresponsive_connection_has_a_bounded_timeout(self):
  class Client:
   def __init__(self,*args):pass
   async def __aenter__(self):await asyncio.Event().wait()
   async def __aexit__(self,*args):pass
  async def audio():
   if False:yield b'',0
  started=time.monotonic()
  with patch.object(stream_module,'AsyncTcpClient',Client),patch.object(stream_module,'CONNECT_TIMEOUT_SECONDS',.02,create=True):
   with self.assertRaises(TimeoutError):await asyncio.wait_for(detect_stream(audio(),'localhost',1,'ehi_nira_it'),.2)
  self.assertLess(time.monotonic()-started,.1)
if __name__=='__main__':unittest.main()
