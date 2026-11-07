#pragma once
#include <cstdint>
#include <string>

namespace nyra {
enum class AlarmIndicatorState { UNKNOWN = 0, DISARMED, ARMING, ARMED };

inline AlarmIndicatorState alarm_indicator_state(const std::string &state) {
  if (state == "disarmed") return AlarmIndicatorState::DISARMED;
  if (state == "arming") return AlarmIndicatorState::ARMING;
  if (state == "armed_away" || state == "armed_home" || state == "armed_night" ||
      state == "armed_vacation" || state == "armed_custom_bypass" ||
      state == "pending" || state == "triggered") return AlarmIndicatorState::ARMED;
  return AlarmIndicatorState::UNKNOWN;
}

// The front battery pixels (1, 0, n-1) are never touched by this overlay.
template<typename SetPixel>
void render_alarm_indicator(int n, int count, bool enabled, AlarmIndicatorState state,
                            uint32_t now, SetPixel set_pixel) {
  if (!enabled || n < 5) return;
  count = count == 3 && n >= 6 ? 3 : 2;
  const int start = n / 2 - (count == 3 ? 1 : 0);
  uint8_t r = 0, g = 0;
  if (state == AlarmIndicatorState::ARMED) r = 255;
  else if (state != AlarmIndicatorState::DISARMED && (now / 1000u) % 2u == 0u) {
    r = 255; g = 160;
  }
  for (int i = 0; i < count; ++i) set_pixel(start + i, r, g, uint8_t(0));
}

inline bool idle_indicator_eligible(bool enabled, bool connected, bool idle_phase,
                                    bool owned, bool voice, bool alert, bool identity,
                                    bool announcement, bool transient, bool native_timer) {
  return enabled && connected && idle_phase && !owned && !voice && !alert &&
         !identity && !announcement && !transient && !native_timer;
}
}  // namespace nyra
