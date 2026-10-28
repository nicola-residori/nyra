#pragma once
#include <cstdint>
#include <string>

namespace nyra {
// Native conversation audio is uncorrelated at the media-player boundary.
// Capture a token when a VA event arrives and recheck when its deferred work runs.
class ConversationOutputGate {
 public:
  void arm() { ++epoch_; armed_ = true; enabled_ = false; }
  bool begin() { if (!armed_) return false; enabled_ = true; return true; }
  void invalidate() { ++epoch_; armed_ = false; enabled_ = false; }
  uint32_t token() const { return epoch_; }
  bool enabled() const { return enabled_; }
  template<typename Callback> void dispatch(uint32_t token, Callback callback) const {
    if (enabled_ && token == epoch_) callback();
  }
 private:
  uint32_t epoch_{0};
  bool armed_{false};
  bool enabled_{false};
};

// Platform-independent ownership core, exercised as native C++ in pytest.
struct AlertState {
  uint32_t epoch{0};
  uint32_t started{0};
  uint32_t limit{60000};
  bool active{false};
  bool heard{false};
  bool call{false};
  std::string job;
  std::string state{"IDLE"};
  bool start(const std::string &id, uint32_t expected_epoch, uint32_t duration,
             bool is_call, uint32_t now) {
    if (active || id == job || expected_epoch != epoch || id.empty()) return false;
    job = id;
    started = now;
    limit = duration > 60000 ? 60000 : (duration < 1000 ? 1000 : duration);
    call = is_call;
    active = true;
    heard = false;
    state = "ACCEPTED";
    return true;
  }
  void playing() { if (active) { heard = true; state = "PLAYING"; } }
  void ended() { if (active && call && heard) { active = false; state = "COMPLETED"; } }
  bool tick(uint32_t now) {
    if (!active || uint32_t(now - started) < limit) return false;
    active = false;
    state = heard ? "COMPLETED" : "FAILED";
    return true;
  }
  void stop() { if (active) { active = false; state = "STOPPED"; } }
  void wake() { ++epoch; stop(); }
};
}
