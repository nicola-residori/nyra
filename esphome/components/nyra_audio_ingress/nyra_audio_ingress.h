#pragma once

#include <atomic>
#include <deque>
#include <memory>
#include <string>
#include <vector>

#include "esp_websocket_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include "esphome/components/audio/audio_transfer_buffer.h"
#include "esphome/components/microphone/microphone_source.h"
#include "esphome/components/ring_buffer/ring_buffer.h"
#include "esphome/core/automation.h"
#include "esphome/core/component.h"
#include "esphome/core/helpers.h"
#include "voice_activity_detector.h"

namespace esphome::nyra_audio_ingress {

enum class StreamState : uint8_t {
  IDLE,
  CONNECTING,
  WAIT_STARTED,
  STREAMING,
  WAIT_CHUNK_ACK,
  WAIT_RESULT,
  CLOSING,
};

enum class TransportCommandType : uint8_t { CONNECT, TEXT, BINARY };
enum class ChunkQueueResult : uint8_t { EMPTY, QUEUED, BUSY };

struct TransportCommand {
  TransportCommandType type;
  std::string payload;
  std::string headers;
  std::vector<uint8_t> binary;
};

class NyraAudioIngress : public Component {
 public:
  static constexpr size_t MAX_QUEUED_AUDIO_BYTES = 64 * 1024;
  static constexpr size_t MAX_TRANSPORT_CHUNK_BYTES = 16 * 1024;
  static constexpr size_t MAX_RESPONSE_BYTES = 16 * 1024;
  static constexpr size_t MAX_RESPONSE_QUEUE = 4;
  static constexpr size_t MAX_TRANSPORT_COMMANDS = 4;
  static constexpr uint32_t ACK_TIMEOUT_MS = 5000;

  void set_microphone_source(microphone::MicrophoneSource *source) { this->microphone_ = source; }
  void set_url(const std::string &value) { this->url_ = value; }
  void set_token(const std::string &value) { this->token_ = value; }
  void set_source_id(const std::string &value) { this->source_id_ = value; }
  void set_language(const std::string &value) { this->language_ = value; }
  void set_timeout_ms(uint32_t value) { this->timeout_ms_ = value; }
  void set_speech_rms(uint32_t value) { this->vad_config_.speech_rms = value; }
  void set_continuation_rms(uint32_t value) { this->vad_config_.continuation_rms = value; }
  void set_speech_on_ms(uint32_t value) { this->vad_config_.speech_on_ms = value; }
  void set_trailing_silence_ms(uint32_t value) { this->vad_config_.trailing_silence_ms = value; }
  void set_no_speech_timeout_ms(uint32_t value) { this->vad_config_.no_speech_timeout_ms = value; }
  void set_max_capture_duration_ms(uint32_t value) { this->vad_config_.max_duration_ms = value; }

  void add_on_accepted_callback(std::function<void()> &&callback) {
    this->accepted_callbacks_.add(std::move(callback));
  }
  void add_on_rejected_callback(std::function<void()> &&callback) {
    this->rejected_callbacks_.add(std::move(callback));
  }
  void add_on_failed_callback(std::function<void()> &&callback) {
    this->failed_callbacks_.add(std::move(callback));
  }

  void setup() override;
  void loop() override;
  void dump_config() override;
  void on_shutdown() override;
  float get_setup_priority() const override { return setup_priority::AFTER_WIFI; }

  void start_identification_stream();
  void start_enrollment_capture();
  void start_wake_word_capture();
  void end_stream();

 protected:
  friend class AcceptedTrigger;
  friend class RejectedTrigger;
  friend class FailedTrigger;

  static void websocket_event_(void *args, esp_event_base_t base, int32_t event_id, void *event_data);
  static void transport_task_entry_(void *args);
  void on_microphone_data_(const std::vector<uint8_t> &data);
  void start_stream_(const char *purpose, bool enrollment_capture);
  void handle_response_(const std::string &message);
  bool send_start_();
  bool send_end_();
  ChunkQueueResult send_next_chunk_();
  bool queue_transport_command_(TransportCommand &&command);
  bool take_transport_command_(TransportCommand &command);
  void clear_transport_commands_();
  void transport_task_loop_();
  void close_transport_worker_();
  void request_transport_close_();
  void fail_(const char *reason);
  void finish_(bool accepted, bool rejected);
  void complete_finish_();
  void clear_queues_();
  std::string take_response_();

  microphone::MicrophoneSource *microphone_{nullptr};
  esp_websocket_client_handle_t websocket_{nullptr};
  SemaphoreHandle_t queue_mutex_{nullptr};
  SemaphoreHandle_t transport_mutex_{nullptr};
  TaskHandle_t transport_task_{nullptr};
  std::deque<std::string> response_queue_;
  std::deque<TransportCommand> transport_commands_;
  std::unique_ptr<audio::RingBufferAudioSource> audio_source_;
  std::weak_ptr<ring_buffer::RingBuffer> audio_ring_buffer_;
  std::string receive_buffer_;
  bool receiving_text_message_{false};

  std::string url_;
  std::string token_;
  std::string headers_;
  std::string source_id_;
  std::string language_;
  std::string audio_stream_id_;
  std::string capture_purpose_{"IDENTIFICATION"};

  std::atomic<bool> capture_active_{false};
  std::atomic<bool> connected_event_{false};
  std::atomic<bool> disconnected_event_{false};
  std::atomic<bool> overflow_event_{false};
  std::atomic<bool> protocol_error_event_{false};
  std::atomic<bool> send_failed_event_{false};
  std::atomic<bool> close_requested_{false};
  std::atomic<bool> stop_transport_task_{false};
  std::atomic<bool> transport_task_stopped_{false};
  std::atomic<bool> closing_transport_{false};
  std::atomic<bool> transport_closed_event_{false};
  bool end_requested_{false};
  bool awaiting_chunk_ack_{false};
  bool terminal_accepted_{false};
  bool terminal_rejected_{false};
  bool enrollment_capture_{false};
  StreamState state_{StreamState::IDLE};
  uint32_t timeout_ms_{30000};
  uint32_t stream_started_ms_{0};
  uint32_t last_progress_ms_{0};
  VoiceActivityConfig vad_config_{};
  VoiceActivityDetector vad_{};

  CallbackManager<void()> accepted_callbacks_;
  CallbackManager<void()> rejected_callbacks_;
  CallbackManager<void()> failed_callbacks_;
};

class AcceptedTrigger : public Trigger<> {
 public:
  explicit AcceptedTrigger(NyraAudioIngress *parent) {
    parent->add_on_accepted_callback([this]() { this->trigger(); });
  }
};

class RejectedTrigger : public Trigger<> {
 public:
  explicit RejectedTrigger(NyraAudioIngress *parent) {
    parent->add_on_rejected_callback([this]() { this->trigger(); });
  }
};

class FailedTrigger : public Trigger<> {
 public:
  explicit FailedTrigger(NyraAudioIngress *parent) {
    parent->add_on_failed_callback([this]() { this->trigger(); });
  }
};

}  // namespace esphome::nyra_audio_ingress
