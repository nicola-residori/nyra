# Pinned native Voice Assistant guard

Vendored from ESPHome **2026.8.2** (`esphome/components/voice_assistant`).
Upstream license is retained in `LICENSE` (GPLv3 C++ runtime / MIT Python).
The Python schema/code generator is unchanged. Runtime changes are deliberately
limited to local conversation-output invalidation:

- Arm a fresh token only when a new pipeline is requested; enable on RUN_START.
- Invalidate on every request_stop, including wake and alert takeover.
- Reject late native INTENT_PROGRESS/TTS ingress while invalidated.
- Capture/recheck the token before immediate streaming URL and deferred TTS
  start/end playback callbacks, so an old callback cannot play after a new wake.

The reusable gate is in the nyra_alerts component and has native executable tests.
Use the complete source in firmware builds. Do not remove this override on an
ESPHome upgrade until equivalent upstream protection is verified. Rebase the small
runtime patch explicitly and rerun native, full suite and full ESP32-S3 builds.
No installation secrets are present.
