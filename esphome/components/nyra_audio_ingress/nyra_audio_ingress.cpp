#include "nyra_audio_ingress.h"

#include <algorithm>
#include <cstdio>

#include "esp_random.h"
#include "esp_transport_ws.h"
#include "esphome/components/json/json_util.h"
#include "esphome/components/network/util.h"
#include "esphome/core/log.h"

namespace esphome::nyra_audio_ingress {

static const char *const TAG = "nyra_audio_ingress";

void NyraAudioIngress::setup() {
  this->queue_mutex_ = xSemaphoreCreateMutex();
  this->transport_mutex_ = xSemaphoreCreateMutex();
  std::shared_ptr<ring_buffer::RingBuffer> audio_ring_buffer =
      ring_buffer::RingBuffer::create(MAX_QUEUED_AUDIO_BYTES);
  if (audio_ring_buffer != nullptr) {
    this->audio_source_ =
        audio::RingBufferAudioSource::create(audio_ring_buffer, MAX_TRANSPORT_CHUNK_BYTES, sizeof(int16_t));
    this->audio_ring_buffer_ = audio_ring_buffer;
  }
  if (this->queue_mutex_ == nullptr || this->transport_mutex_ == nullptr || this->microphone_ == nullptr ||
      this->audio_source_ == nullptr) {
    ESP_LOGE(TAG, "Cannot initialize audio ingress");
    this->mark_failed();
    return;
  }
  if (xTaskCreate(NyraAudioIngress::transport_task_entry_, "nyra_audio_ws", 8192, this, 4,
                  &this->transport_task_) != pdPASS) {
    ESP_LOGE(TAG, "Cannot create audio ingress transport task");
    this->mark_failed();
    return;
  }

  this->microphone_->add_data_callback(
      [this](const std::vector<uint8_t> &data) { this->on_microphone_data_(data); });
}

void NyraAudioIngress::dump_config() {
  ESP_LOGCONFIG(TAG, "Nyra audio ingress:");
  ESP_LOGCONFIG(TAG, "  URL: %s", this->url_.c_str());
  ESP_LOGCONFIG(TAG, "  Source: %s", this->source_id_.c_str());
  ESP_LOGCONFIG(TAG, "  Language: %s", this->language_.c_str());
  ESP_LOGCONFIG(TAG, "  Queue limit: %u bytes", static_cast<unsigned>(MAX_QUEUED_AUDIO_BYTES));
}

void NyraAudioIngress::start_identification_stream() {
  this->start_stream_("IDENTIFICATION", false);
}

void NyraAudioIngress::start_enrollment_capture() {
  this->start_stream_("ENROLLMENT_CAPTURE", true);
}

void NyraAudioIngress::start_wake_word_capture() {
  this->start_stream_("WAKE_WORD_CAPTURE", true);
}

void NyraAudioIngress::start_stream_(const char *purpose, bool enrollment_capture) {
  if (this->state_ != StreamState::IDLE) {
    ESP_LOGW(TAG, "Ignoring overlapping audio stream");
    if (enrollment_capture)
      this->failed_callbacks_.call();
    return;
  }
  if (!network::is_connected() || this->transport_task_stopped_.load()) {
    this->failed_callbacks_.call();
    return;
  }

  this->clear_queues_();
  this->clear_transport_commands_();
  char id[160];
  snprintf(id, sizeof(id), "aud_%s_%08lX_%08lX", this->source_id_.c_str(),
           static_cast<unsigned long>(millis()), static_cast<unsigned long>(esp_random()));
  this->audio_stream_id_ = id;
  this->capture_purpose_ = purpose;
  this->enrollment_capture_ = enrollment_capture;
  if (this->enrollment_capture_) {
    this->vad_ = VoiceActivityDetector(this->vad_config_);
    this->vad_.reset(millis());
  }
  this->headers_ = "Authorization: Bearer " + this->token_ + "\r\n";

  this->end_requested_ = false;
  this->awaiting_chunk_ack_ = false;
  this->connected_event_.store(false);
  this->disconnected_event_.store(false);
  this->overflow_event_.store(false);
  this->protocol_error_event_.store(false);
  this->send_failed_event_.store(false);
  this->transport_closed_event_.store(false);
  this->stream_started_ms_ = millis();
  this->last_progress_ms_ = this->stream_started_ms_;
  this->state_ = StreamState::CONNECTING;

  TransportCommand connect{TransportCommandType::CONNECT, this->url_, this->headers_, {}};
  if (!this->queue_transport_command_(std::move(connect))) {
    this->fail_("connect queue");
    return;
  }
  this->capture_active_.store(true);
}

void NyraAudioIngress::end_stream() {
  if (this->state_ == StreamState::IDLE)
    return;
  this->capture_active_.store(false);
  this->end_requested_ = true;
}

void NyraAudioIngress::loop() {
  if (this->state_ == StreamState::IDLE)
    return;
  if (this->state_ == StreamState::CLOSING) {
    if (this->transport_closed_event_.exchange(false))
      this->complete_finish_();
    return;
  }

  for (std::string response = this->take_response_(); !response.empty(); response = this->take_response_())
    this->handle_response_(response);
  if (this->state_ == StreamState::CLOSING || this->state_ == StreamState::IDLE)
    return;

  const uint32_t now = millis();
  if (now - this->stream_started_ms_ > this->timeout_ms_) {
    this->fail_("stream timeout");
    return;
  }
  if (this->overflow_event_.exchange(false)) {
    this->fail_("audio queue overflow");
    return;
  }
  if (this->protocol_error_event_.exchange(false)) {
    this->fail_("invalid response frame");
    return;
  }
  if (this->send_failed_event_.exchange(false)) {
    this->fail_("transport send");
    return;
  }
  if (this->disconnected_event_.exchange(false)) {
    this->fail_("disconnected");
    return;
  }

  if (this->state_ == StreamState::CONNECTING && this->connected_event_.load()) {
    if (this->send_start_()) {
      this->connected_event_.store(false);
      this->state_ = StreamState::WAIT_STARTED;
      this->last_progress_ms_ = now;
    }
  }

  if ((this->state_ == StreamState::WAIT_STARTED || this->state_ == StreamState::WAIT_CHUNK_ACK ||
       this->state_ == StreamState::WAIT_RESULT) &&
      now - this->last_progress_ms_ > ACK_TIMEOUT_MS) {
    this->fail_("ack timeout");
    return;
  }

  if (this->state_ == StreamState::STREAMING) {
    const ChunkQueueResult chunk = this->send_next_chunk_();
    if (chunk == ChunkQueueResult::QUEUED) {
      this->awaiting_chunk_ack_ = true;
      this->state_ = StreamState::WAIT_CHUNK_ACK;
      this->last_progress_ms_ = now;
      return;
    }
    if (chunk == ChunkQueueResult::EMPTY && this->end_requested_ && this->send_end_()) {
      this->state_ = StreamState::WAIT_RESULT;
      this->last_progress_ms_ = now;
    }
  }
}

void NyraAudioIngress::handle_response_(const std::string &message) {
  bool valid = json::parse_json(message, [this](JsonObject root) {
    const std::string type = root["type"] | "";
    const std::string stream_id = root["audio_stream_id"] | "";
    if (stream_id != this->audio_stream_id_)
      return false;
    if (type == "STARTED" && this->state_ == StreamState::WAIT_STARTED) {
      this->state_ = StreamState::STREAMING;
      this->last_progress_ms_ = millis();
      return true;
    }
    if (type == "CHUNK" && this->state_ == StreamState::WAIT_CHUNK_ACK) {
      this->awaiting_chunk_ack_ = false;
      this->state_ = StreamState::STREAMING;
      this->last_progress_ms_ = millis();
      return true;
    }
    if (type == "RESULT" && this->state_ == StreamState::WAIT_RESULT) {
      if (this->capture_purpose_ == "ENROLLMENT_CAPTURE" ||
          this->capture_purpose_ == "WAKE_WORD_CAPTURE") {
        const std::string status = root["result"]["status"] | "";
        if (status == "ACCEPTED")
          this->finish_(true, false);
        else if (status == "REJECTED")
          this->finish_(false, true);
        else
          this->finish_(false, false);
      } else {
        const std::string outcome = root["result"]["outcome"] | "";
        if (outcome == "IDENTIFIED")
          this->finish_(true, false);
        else if (outcome == "NOT_RECOGNIZED")
          this->finish_(false, true);
        else
          this->finish_(false, false);
      }
      return true;
    }
    if (type == "ERROR") {
      this->finish_(false, false);
      return true;
    }
    return false;
  });
  if (!valid && this->state_ != StreamState::IDLE)
    this->fail_("invalid response");
}

bool NyraAudioIngress::send_start_() {
  auto message = json::build_json([this](JsonObject root) {
    root["type"] = "START";
    root["audio_stream_id"] = this->audio_stream_id_;
    root["purpose"] = this->capture_purpose_;
    root["source_id"] = this->source_id_;
    root["language"] = this->language_;
    root["audio_format"] = "pcm_s16le";
    root["sample_rate"] = 16000;
    root["channels"] = 1;
  });
  return this->queue_transport_command_({TransportCommandType::TEXT, std::move(message), {}, {}});
}

bool NyraAudioIngress::send_end_() {
  auto message = json::build_json([this](JsonObject root) {
    root["type"] = "END";
    root["audio_stream_id"] = this->audio_stream_id_;
  });
  return this->queue_transport_command_({TransportCommandType::TEXT, std::move(message), {}, {}});
}

ChunkQueueResult NyraAudioIngress::send_next_chunk_() {
  if (xSemaphoreTake(this->transport_mutex_, 0) != pdTRUE) {
    return ChunkQueueResult::BUSY;
  }
  if (this->transport_commands_.size() >= MAX_TRANSPORT_COMMANDS) {
    xSemaphoreGive(this->transport_mutex_);
    return ChunkQueueResult::BUSY;
  }
  xSemaphoreGive(this->transport_mutex_);

  if (this->audio_source_ == nullptr)
    return ChunkQueueResult::EMPTY;
  this->audio_source_->fill(0, false);
  const size_t available = std::min(this->audio_source_->available(), MAX_TRANSPORT_CHUNK_BYTES);
  if (available == 0)
    return ChunkQueueResult::EMPTY;

  TransportCommand command{TransportCommandType::BINARY, {}, {}, {}};
  command.binary.assign(this->audio_source_->data(), this->audio_source_->data() + available);
  if (this->enrollment_capture_ && available >= sizeof(int16_t)) {
    const auto decision = this->vad_.update(
        reinterpret_cast<const int16_t *>(command.binary.data()), available / sizeof(int16_t), millis());
    if (decision == CaptureDecision::COMPLETE || decision == CaptureDecision::NO_SPEECH_TIMEOUT ||
        decision == CaptureDecision::MAX_DURATION) {
      this->capture_active_.store(false);
      this->end_requested_ = true;
    }
  }
  this->audio_source_->consume(available);
  if (!this->queue_transport_command_(std::move(command))) {
    this->send_failed_event_.store(true);
  }
  return ChunkQueueResult::QUEUED;
}

bool NyraAudioIngress::queue_transport_command_(TransportCommand &&command) {
  if (this->transport_task_ == nullptr || xSemaphoreTake(this->transport_mutex_, pdMS_TO_TICKS(5)) != pdTRUE)
    return false;
  if (this->transport_commands_.size() >= MAX_TRANSPORT_COMMANDS) {
    xSemaphoreGive(this->transport_mutex_);
    return false;
  }
  this->transport_commands_.push_back(std::move(command));
  xSemaphoreGive(this->transport_mutex_);
  xTaskNotifyGive(this->transport_task_);
  return true;
}

bool NyraAudioIngress::take_transport_command_(TransportCommand &command) {
  if (xSemaphoreTake(this->transport_mutex_, pdMS_TO_TICKS(50)) != pdTRUE)
    return false;
  if (this->transport_commands_.empty()) {
    xSemaphoreGive(this->transport_mutex_);
    return false;
  }
  command = std::move(this->transport_commands_.front());
  this->transport_commands_.pop_front();
  xSemaphoreGive(this->transport_mutex_);
  return true;
}

void NyraAudioIngress::clear_transport_commands_() {
  if (this->transport_mutex_ == nullptr || xSemaphoreTake(this->transport_mutex_, pdMS_TO_TICKS(5)) != pdTRUE)
    return;
  this->transport_commands_.clear();
  xSemaphoreGive(this->transport_mutex_);
}

void NyraAudioIngress::transport_task_entry_(void *args) {
  static_cast<NyraAudioIngress *>(args)->transport_task_loop_();
}

void NyraAudioIngress::transport_task_loop_() {
  while (true) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    if (this->stop_transport_task_.load()) {
      this->close_transport_worker_();
      this->transport_task_stopped_.store(true);
      vTaskDelete(nullptr);
      return;
    }
    if (this->close_requested_.exchange(false)) {
      this->close_transport_worker_();
      this->transport_closed_event_.store(true);
      continue;
    }

    TransportCommand command{TransportCommandType::TEXT, {}, {}, {}};
    while (this->take_transport_command_(command)) {
      bool success = false;
      if (command.type == TransportCommandType::CONNECT) {
        this->close_transport_worker_();
        esp_websocket_client_config_t config = {};
        config.uri = command.payload.c_str();
        config.headers = command.headers.c_str();
        config.transport = WEBSOCKET_TRANSPORT_OVER_TCP;
        config.disable_auto_reconnect = true;
        config.network_timeout_ms = ACK_TIMEOUT_MS;
        config.buffer_size = 2048;
        config.task_stack = 6144;
        this->websocket_ = esp_websocket_client_init(&config);
        if (this->websocket_ != nullptr) {
          esp_websocket_register_events(this->websocket_, WEBSOCKET_EVENT_ANY,
                                        NyraAudioIngress::websocket_event_, this);
          success = esp_websocket_client_start(this->websocket_) == ESP_OK;
        }
      } else if (this->websocket_ != nullptr && command.type == TransportCommandType::TEXT) {
        const int sent = esp_websocket_client_send_text(this->websocket_, command.payload.c_str(),
                                                        command.payload.size(), pdMS_TO_TICKS(ACK_TIMEOUT_MS));
        success = sent == static_cast<int>(command.payload.size());
      } else if (this->websocket_ != nullptr && command.type == TransportCommandType::BINARY) {
        const int sent = esp_websocket_client_send_bin(
            this->websocket_, reinterpret_cast<const char *>(command.binary.data()), command.binary.size(),
            pdMS_TO_TICKS(ACK_TIMEOUT_MS));
        success = sent == static_cast<int>(command.binary.size());
      }

      if (!success) {
        this->send_failed_event_.store(true);
        this->close_transport_worker_();
        break;
      }
    }
  }
}

void NyraAudioIngress::request_transport_close_() {
  this->close_requested_.store(true);
  if (this->transport_task_ != nullptr)
    xTaskNotifyGive(this->transport_task_);
}

void NyraAudioIngress::close_transport_worker_() {
  if (this->websocket_ == nullptr)
    return;
  this->closing_transport_.store(true);
  esp_websocket_client_stop(this->websocket_);
  esp_websocket_client_destroy(this->websocket_);
  this->websocket_ = nullptr;
  this->closing_transport_.store(false);
}

void NyraAudioIngress::on_microphone_data_(const std::vector<uint8_t> &data) {
  if (!this->capture_active_.load() || data.empty() || data.size() > MAX_QUEUED_AUDIO_BYTES)
    return;
  std::shared_ptr<ring_buffer::RingBuffer> audio_ring_buffer = this->audio_ring_buffer_.lock();
  if (audio_ring_buffer == nullptr)
    return;
  if (audio_ring_buffer->write_without_replacement(data.data(), data.size(), 0, false) != data.size())
    this->overflow_event_.store(true);
}

void NyraAudioIngress::websocket_event_(void *args, esp_event_base_t base, int32_t event_id, void *event_data) {
  auto *self = static_cast<NyraAudioIngress *>(args);
  auto *data = static_cast<esp_websocket_event_data_t *>(event_data);
  const auto event = static_cast<esp_websocket_event_id_t>(event_id);
  if (event == WEBSOCKET_EVENT_CONNECTED) {
    if (!self->closing_transport_.load())
      self->connected_event_.store(true);
    return;
  }
  if (event == WEBSOCKET_EVENT_DISCONNECTED || event == WEBSOCKET_EVENT_CLOSED || event == WEBSOCKET_EVENT_ERROR) {
    if (!self->closing_transport_.load())
      self->disconnected_event_.store(true);
    return;
  }
  if (event != WEBSOCKET_EVENT_DATA || data == nullptr)
    return;
  const uint8_t opcode = static_cast<uint8_t>(data->op_code) & 0x0F;
  if (opcode != WS_TRANSPORT_OPCODES_TEXT && opcode != WS_TRANSPORT_OPCODES_CONT)
    return;
  if (xSemaphoreTake(self->queue_mutex_, 0) != pdTRUE) {
    self->protocol_error_event_.store(true);
    return;
  }

  bool invalid = false;
  if (opcode == WS_TRANSPORT_OPCODES_TEXT && data->payload_offset == 0) {
    invalid = self->receiving_text_message_;
    self->receive_buffer_.clear();
    self->receiving_text_message_ = true;
  } else if (!self->receiving_text_message_) {
    invalid = true;
  }
  if (!invalid && self->receive_buffer_.size() + static_cast<size_t>(data->data_len) > MAX_RESPONSE_BYTES)
    invalid = true;

  if (invalid) {
    self->receive_buffer_.clear();
    self->receiving_text_message_ = false;
    self->protocol_error_event_.store(true);
    xSemaphoreGive(self->queue_mutex_);
    return;
  }
  if (data->data_len > 0)
    self->receive_buffer_.append(data->data_ptr, data->data_len);

  const bool frame_complete =
      data->payload_len == 0 || data->payload_offset + data->data_len >= data->payload_len;
  if (frame_complete && data->fin) {
    if (self->response_queue_.size() >= MAX_RESPONSE_QUEUE || self->receive_buffer_.empty()) {
      self->protocol_error_event_.store(true);
    } else {
      self->response_queue_.push_back(std::move(self->receive_buffer_));
    }
    self->receive_buffer_.clear();
    self->receiving_text_message_ = false;
  }
  xSemaphoreGive(self->queue_mutex_);
}

std::string NyraAudioIngress::take_response_() {
  std::string response;
  if (xSemaphoreTake(this->queue_mutex_, 0) != pdTRUE)
    return response;
  if (!this->response_queue_.empty()) {
    response = std::move(this->response_queue_.front());
    this->response_queue_.pop_front();
  }
  xSemaphoreGive(this->queue_mutex_);
  return response;
}

void NyraAudioIngress::fail_(const char *reason) {
  ESP_LOGW(TAG, "Stream failed: %s", reason);
  this->finish_(false, false);
}

void NyraAudioIngress::finish_(bool accepted, bool rejected) {
  this->capture_active_.store(false);
  this->terminal_accepted_ = accepted;
  this->terminal_rejected_ = rejected;
  this->state_ = StreamState::CLOSING;
  this->clear_transport_commands_();
  this->request_transport_close_();
  this->clear_queues_();
}

void NyraAudioIngress::complete_finish_() {
  const bool completed_enrollment_capture = this->enrollment_capture_;
  this->state_ = StreamState::IDLE;
  this->enrollment_capture_ = false;
  if (completed_enrollment_capture) {
    if (this->terminal_accepted_)
      this->accepted_callbacks_.call();
    else if (this->terminal_rejected_)
      this->rejected_callbacks_.call();
    else
      this->failed_callbacks_.call();
  }
  this->terminal_accepted_ = false;
  this->terminal_rejected_ = false;
}

void NyraAudioIngress::clear_queues_() {
  if (this->audio_source_ != nullptr)
    this->audio_source_->clear_buffered_data();
  if (this->queue_mutex_ == nullptr || xSemaphoreTake(this->queue_mutex_, pdMS_TO_TICKS(5)) != pdTRUE)
    return;
  this->response_queue_.clear();
  this->receive_buffer_.clear();
  this->receiving_text_message_ = false;
  xSemaphoreGive(this->queue_mutex_);
}

void NyraAudioIngress::on_shutdown() {
  this->capture_active_.store(false);
  this->stop_transport_task_.store(true);
  if (this->transport_task_ != nullptr)
    xTaskNotifyGive(this->transport_task_);
  for (uint16_t wait = 0; wait < 500 && !this->transport_task_stopped_.load(); wait++)
    vTaskDelay(pdMS_TO_TICKS(10));
  if (!this->transport_task_stopped_.load())
    return;
  if (this->queue_mutex_ != nullptr) {
    vSemaphoreDelete(this->queue_mutex_);
    this->queue_mutex_ = nullptr;
  }
  if (this->transport_mutex_ != nullptr) {
    vSemaphoreDelete(this->transport_mutex_);
    this->transport_mutex_ = nullptr;
  }
}

}  // namespace esphome::nyra_audio_ingress
