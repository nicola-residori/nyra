# Alarm indicator implementation

Execute inline using TDD. Spec: docs/superpowers/specs/2026-10-30-alarm-indicator-design.md.
User selected idle-only coexistence with battery; two opposite red LEDs chosen.

1. RED native C++ overlay/state/idle-priority tests. GREEN header, base globals and
   overlay hook; optional HA text-sensor package and conservative local idle restore.
   Keep default non-opted-in speaker behavior and existing battery pixels unchanged.
2. Verify optional configuration examples and test the actual merged YAML where
   practical. Full suite, diff check, independent review. Reproduce/fix important findings.
3. Configure the known HA alarm only in private deployment entrypoints. Build both
   devices with ESPHome2026.10.1, commit/push green, back up sources/config/automation,
   OTA and verify API stability/state. Remove only the battery automation's forced
   effect action after firmware is ready; preserve number updates and unrelated YAML.
4. Verify disarmed state and idle/interaction restoration. Armed/unknown pixel cases
   are simulated; real armed display acceptance waits for normal user alarm use.
   Main remains unmerged. Record evidence, limits and rollback including automation.
