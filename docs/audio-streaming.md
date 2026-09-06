# M3 audio streaming wire protocol

Task 10 implements `GET /v1/audio/stream` as a WebSocket endpoint on both
Router and Speaker-ID. One WebSocket carries one recording. Home Assistant
connects to Router; only Router connects to Speaker-ID. Use a single application
worker per service: the active-stream registry is process-local.

Configure Router with `NYRA_SPEAKER_ID_STREAM_URL` (for example,
`ws://speaker-id:8090/v1/audio/stream`). No host is assumed by default; an
unconfigured relay returns `SPEAKER_ID_UNAVAILABLE`. Router accepts the same
`Authorization: Bearer ...` header configured by `NYRA_ROUTER_INGRESS_TOKEN`
as its other ingress endpoints. Speaker-ID follows the component contract's
trusted private network boundary.

Send a JSON START message, then binary audio frames, then a JSON END message.
Wait for each acknowledgement before sending the next frame (backpressure).

```json
{
  "type": "START",
  "audio_stream_id": "aud_<unique recording ID>",
  "purpose": "IDENTIFICATION",
  "request_id": "req_<request ID>",
  "session_id": "ses_<conversation ID>",
  "source_id": "speaker-source",
  "trace_id": "trc_<trace ID>",
  "span_id": "upstream-operation-span",
  "parent_span_id": "upstream-parent-span",
  "language": "en",
  "audio_format": "pcm_s16le",
  "sample_rate": 16000,
  "channels": 1
}
```

`audio_stream_id`, `purpose`, `trace_id`, and `span_id` are required. Supported
purposes and additional requirements:

- `IDENTIFICATION`: `request_id`.
- `ENROLLMENT`: `enrollment_session_id`, canonical authenticated `user_id`.
- `WAKE_WORD_CAPTURE`: `wake_word_session_id`, authenticated `user_id`,
  `wake_word_text`, `language`.

Conversation `session_id` does not substitute for a typed operation ID.
Enrollment and wake capture metadata must originate from the authenticated HA
workflow. This task provides the transport; HA workflow implementation is Task 11.

Audio defaults to a WAV byte stream (`audio_format: "wav"`). For raw microphone
samples use `pcm_s16le`, sample rate 8000–96000 Hz, and one or two channels.
WAV headers must satisfy the same rate/channel limits and use 16-bit samples.
Both formats are limited to 30 seconds of decoded audio before preprocessing.
Only Speaker-ID decodes and preprocesses audio. Router never writes or builds a
complete recording. Speaker-ID retains raw bytes only in bounded memory and
persists processed domain audio according to its existing storage/retention rules.

Server responses:

```json
{"type":"STARTED","audio_stream_id":"aud_<unique recording ID>"}
{"type":"CHUNK","audio_stream_id":"aud_<unique recording ID>"}
```

Terminate with `{"type":"END","audio_stream_id":"aud_<unique recording ID>"}`.
The response is `{"type":"RESULT","audio_stream_id":"...","result":{...}}`.
Identification results contain only the minimal typed decision fields; candidate
scores remain in Speaker-ID diagnostics. Enrollment and wake capture return
`ACCEPTED`, `REJECTED`, or `FAILED` status. A wake-word session accepts at most one
permanent sample even if another stream ID is submitted for the same session.

Technical failures use `{"type":"ERROR","audio_stream_id":"...","outcome":"FAILED",
"reason_code":"..."}` followed by close code 4400. Authorization failures close
with 4401 before accepting. Unknown IDs, duplicate START, duplicate END, malformed
messages, and late binary frames are rejected. A connection cannot end another
connection's recording. Idle closure after a successful result is normal (1000).

Bounds per application instance: 32 active recordings, 256 KiB per binary frame,
8 MiB cumulative audio per recording, 16 KiB per JSON frame, and 1024 recent closed
IDs. Older closed IDs become unknown, so clients must always generate fresh IDs.
`NYRA_AUDIO_STREAM_TIMEOUT_SECONDS` (default 30 seconds) bounds the stream's
lifetime on each service; it is distinct from Router's biometric identity-resolution
timeout. Downstream work and cleanup are time-bounded. Speaker-ID permits four
outstanding preprocessing/inference jobs, including cancelled jobs until their
worker actually exits; overload fails without queuing unbounded recordings.
Cancelled computation cannot persist a late result.

The automated tests use generated audio and deterministic embedding engines.
Physical HA/ESPHome devices and a downloaded ECAPA model are not required for
Task 10 verification; their integration/provisioning belongs to later M3 tasks.
