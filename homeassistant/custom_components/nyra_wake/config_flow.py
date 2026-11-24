"""Configure the local Nyra provider, validating its advertised model."""
import asyncio
import probatio
from homeassistant.config_entries import ConfigFlow
from wyoming.client import AsyncTcpClient
from wyoming.info import Describe,Info
from . import DOMAIN
SCHEMA=probatio.Schema({probatio.Required('host',default='192.168.0.16'):str,probatio.Required('port',default=10401):int})
class NyraWakeConfigFlow(ConfigFlow,domain=DOMAIN):
 VERSION=1
 async def async_step_user(self,user_input=None):
  errors={}
  if user_input is not None:
   await self.async_set_unique_id(f"{user_input['host']}:{user_input['port']}");self._abort_if_unique_id_configured()
   try:
    async with asyncio.timeout(10):
     async with AsyncTcpClient(user_input['host'],user_input['port']) as client:
      await client.write_event(Describe().event());event=await client.read_event()
      if event is None or not Info.is_type(event.type):raise ValueError('No service information')
      info=Info.from_event(event)
      if not any(m.name=='ehi_nira_it' for p in info.wake for m in p.models):raise ValueError('Expected Ehi Nira model')
   except (OSError,TimeoutError,ValueError):errors['base']='cannot_connect'
   else:return self.async_create_entry(title='Nyra Italian Wake',data=user_input)
  return self.async_show_form(step_id='user',data_schema=SCHEMA,errors=errors)
