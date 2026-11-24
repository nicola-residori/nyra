"""Nyra wake-word provider; PCM remains only in a bounded RAM buffer."""
DOMAIN='nyra_wake'
async def async_setup_entry(hass,entry):
 await hass.config_entries.async_forward_entry_setups(entry,['wake_word'])
 return True
async def async_unload_entry(hass,entry):return await hass.config_entries.async_unload_platforms(entry,['wake_word'])
