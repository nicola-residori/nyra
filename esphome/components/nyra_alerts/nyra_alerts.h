#pragma once
#include <cstdint>
#include <string>

namespace esphome { namespace audio { struct AudioFile; } }

namespace nyra {
// Pure mixer attenuation: no player volume snapshot or automatic resume.
inline int music_duck_db(bool voice, bool announcement, bool alert, bool native_timer, int baseline_db = 9) {
  const int baseline = baseline_db < 0 ? 0 : baseline_db > 20 ? 20 : baseline_db;
  return alert || native_timer ? 60 : voice ? 30 : announcement ? 20 : baseline;
}

using AudioFilePointer = const esphome::audio::AudioFile *;
// Preserve the trained model's cutoff; sensitivity increases are relative to it.
inline uint8_t wake_word_cutoff(uint8_t manifest_cutoff, uint8_t sensitivity) {
  if (sensitivity > 2) sensitivity = 2;
  const uint16_t reduction = 26u * sensitivity;
  return manifest_cutoff > reduction ? static_cast<uint8_t>(manifest_cutoff - reduction) : 1u;
}
// ESPHome 2026.8 accepts AudioFile*, 2026.10 accepts const AudioFile*.
// The legacy runtime only reads this descriptor; modern constness is preserved
// at the callee boundary by its const-pointer signature.
template<typename Player, typename File> void play_asset(Player *player, const File *file) {
  player->play_file(const_cast<File *>(file), true, false);
}

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

// Only explicit disarm resets an intrusion episode. Connectivity loss cannot.
struct IntrusionEpisode {
  bool latched{false};
  int observe(const std::string &state) {
    if (state == "disarmed") { bool was = latched; latched = false; return was ? 2 : 0; }
    if (state != "triggered" || latched) return 0;
    latched = true;
    return 1;
  }
};

// Platform-independent ownership core, exercised as native C++ in pytest.
struct AlertState {
  uint32_t epoch{0};
  uint32_t started{0};
  uint32_t limit{60000};
  bool intrusion{false};
  bool active{false};
  bool heard{false};
  bool call{false};
  std::string job;
  std::string state{"IDLE"};
  bool start(const std::string &id, uint32_t expected_epoch, uint32_t duration,
             bool is_call, uint32_t now) {
    if (active || id == job || expected_epoch != epoch || id.empty()) return false;
    intrusion = false;
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
  bool protected_audio() const { return active && intrusion; }
  bool start_intrusion(uint32_t now) {
    if (active) return false;
    ++epoch;
    const bool accepted = start("intrusion:" + std::to_string(epoch), epoch, 60000, false, now);
    intrusion = accepted;
    return accepted;
  }
  void wake() { if (protected_audio()) return; ++epoch; stop(); }
};
}
