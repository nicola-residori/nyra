"""Wyoming wake detection with command audio retained during verification."""
import asyncio
from contextlib import AsyncExitStack
from wyoming.audio import AudioChunk,AudioStart,AudioStop
from wyoming.client import AsyncTcpClient
from wyoming.wake import Detect,Detection,NotDetected
from wyoming.error import Error
from .audio_buffer import AudioBuffer
CONNECT_TIMEOUT_SECONDS=10
async def detect_stream(stream,host,port,name):
 buffer=AudioBuffer(seconds=8)
 async def next_chunk():
  async for data,ts in stream:
   buffer.append(data,ts)
   return data,ts
  return None
 async with AsyncExitStack() as stack:
  async with asyncio.timeout(CONNECT_TIMEOUT_SECONDS):client=await stack.enter_async_context(AsyncTcpClient(host,port))
  await client.write_event(Detect(names=[name]).event());await client.write_event(AudioStart(rate=16000,width=2,channels=1).event())
  audio_task=asyncio.create_task(next_chunk());wake_task=asyncio.create_task(client.read_event())
  try:
   while True:
    done,_=await asyncio.wait({audio_task,wake_task},return_when=asyncio.FIRST_COMPLETED)
    if wake_task in done:
     event=wake_task.result()
     if event is None:return None,[]
     if Error.is_type(event.type):raise RuntimeError(Error.from_event(event).text)
     if NotDetected.is_type(event.type):return None,[]
     if Detection.is_type(event.type):
      detection=Detection.from_event(event)
      if detection.name!=name:raise RuntimeError('Unexpected wake word returned')
      # Finish the in-flight read, never cancel it: cancellation closes the
      # upstream audio generator and breaks the following STT stage.
      await asyncio.wait_for(audio_task,2)
      start=detection.timestamp if detection.timestamp is not None else 0
      return detection,buffer.after(max(0,start-1000))
     wake_task=asyncio.create_task(client.read_event())
    if audio_task in done:
     item=audio_task.result()
     if item is None:
      await client.write_event(AudioStop().event())
      event=await asyncio.wait_for(wake_task,5)
      if event is not None and Error.is_type(event.type):raise RuntimeError(Error.from_event(event).text)
      if event is not None and Detection.is_type(event.type):
       detection=Detection.from_event(event)
       if detection.name!=name:raise RuntimeError('Unexpected wake word returned')
       return detection,buffer.after(max(0,(detection.timestamp or 0)-1000))
      return None,[]
     data,ts=item
     await client.write_event(AudioChunk(rate=16000,width=2,channels=1,audio=data,timestamp=ts).event())
     audio_task=asyncio.create_task(next_chunk())
  finally:
   # Only abort unfinished upstream reads after failure/end/cancellation.
   # The successful handoff above has already completed its in-flight read.
   for task in (audio_task,wake_task):
    if not task.done():task.cancel()
   await asyncio.gather(audio_task,wake_task,return_exceptions=True)
