#pragma once

#include <cstddef>
#include <cstdint>

namespace esphome::nyra_audio_ingress {

enum class CaptureDecision : uint8_t {
  WAITING_FOR_SPEECH,
  SPEAKING,
  COMPLETE,
  NO_SPEECH_TIMEOUT,
  MAX_DURATION,
};

struct VoiceActivityConfig {
  uint32_t speech_rms{700};
  uint32_t continuation_rms{450};
  uint32_t speech_on_ms{120};
  uint32_t trailing_silence_ms{900};
  uint32_t no_speech_timeout_ms{8000};
  uint32_t max_duration_ms{15000};
};

class VoiceActivityDetector {
 public:
  explicit VoiceActivityDetector(VoiceActivityConfig config = {}) : config_(config) {}

  void reset(uint32_t now_ms) {
    this->started_ms_ = now_ms;
    this->candidate_started_ms_ = now_ms;
    this->last_voice_ms_ = now_ms;
    this->candidate_active_ = false;
    this->speech_started_ = false;
  }

  CaptureDecision update(const int16_t *samples, size_t count, uint32_t now_ms) {
    const uint32_t elapsed = now_ms - this->started_ms_;
    if (this->speech_started_ && elapsed >= this->config_.max_duration_ms)
      return CaptureDecision::MAX_DURATION;

    const uint32_t rms = calculate_rms_(samples, count);
    if (!this->speech_started_) {
      if (elapsed >= this->config_.no_speech_timeout_ms)
        return CaptureDecision::NO_SPEECH_TIMEOUT;
      if (rms < this->config_.speech_rms) {
        this->candidate_active_ = false;
        return CaptureDecision::WAITING_FOR_SPEECH;
      }
      if (!this->candidate_active_) {
        this->candidate_active_ = true;
        this->candidate_started_ms_ = now_ms;
        return CaptureDecision::WAITING_FOR_SPEECH;
      }
      if (now_ms - this->candidate_started_ms_ < this->config_.speech_on_ms)
        return CaptureDecision::WAITING_FOR_SPEECH;
      this->speech_started_ = true;
      this->last_voice_ms_ = now_ms;
      return CaptureDecision::SPEAKING;
    }

    if (rms >= this->config_.continuation_rms)
      this->last_voice_ms_ = now_ms;
    if (now_ms - this->last_voice_ms_ >= this->config_.trailing_silence_ms)
      return CaptureDecision::COMPLETE;
    return CaptureDecision::SPEAKING;
  }

 private:
  static uint32_t calculate_rms_(const int16_t *samples, size_t count) {
    if (samples == nullptr || count == 0)
      return 0;
    uint64_t sum_squares = 0;
    for (size_t index = 0; index < count; index++) {
      const int64_t sample = samples[index];
      sum_squares += static_cast<uint64_t>(sample * sample);
    }
    const uint64_t mean = sum_squares / count;
    uint64_t root = 0;
    uint64_t bit = uint64_t{1} << 62;
    while (bit > mean)
      bit >>= 2;
    uint64_t remainder = mean;
    while (bit != 0) {
      if (remainder >= root + bit) {
        remainder -= root + bit;
        root = (root >> 1) + bit;
      } else {
        root >>= 1;
      }
      bit >>= 2;
    }
    return static_cast<uint32_t>(root);
  }

  VoiceActivityConfig config_;
  uint32_t started_ms_{0};
  uint32_t candidate_started_ms_{0};
  uint32_t last_voice_ms_{0};
  bool candidate_active_{false};
  bool speech_started_{false};
};

}  // namespace esphome::nyra_audio_ingress
