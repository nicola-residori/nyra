import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import automation
from esphome.components import esp32, microphone
from esphome.const import CONF_ID, CONF_MICROPHONE, CONF_TRIGGER_ID
from esphome.core import CORE


CONF_URL = "url"
CONF_TOKEN = "token"
CONF_SOURCE_ID = "source_id"
CONF_LANGUAGE = "language"
CONF_TIMEOUT = "timeout"
CONF_SPEECH_RMS = "speech_rms"
CONF_CONTINUATION_RMS = "continuation_rms"
CONF_SPEECH_ON = "speech_on"
CONF_TRAILING_SILENCE = "trailing_silence"
CONF_NO_SPEECH_TIMEOUT = "no_speech_timeout"
CONF_MAX_CAPTURE_DURATION = "max_capture_duration"
CONF_ON_ACCEPTED = "on_accepted"
CONF_ON_REJECTED = "on_rejected"
CONF_ON_FAILED = "on_failed"

DEPENDENCIES = ["network"]
AUTO_LOAD = ["audio", "json", "ring_buffer"]

nyra_ns = cg.esphome_ns.namespace("nyra_audio_ingress")
NyraAudioIngress = nyra_ns.class_("NyraAudioIngress", cg.Component)
AcceptedTrigger = nyra_ns.class_("AcceptedTrigger", automation.Trigger.template())
RejectedTrigger = nyra_ns.class_("RejectedTrigger", automation.Trigger.template())
FailedTrigger = nyra_ns.class_("FailedTrigger", automation.Trigger.template())


def _validate(config):
    if CORE.target_framework != "esp-idf":
        raise cv.Invalid("nyra_audio_ingress requires the ESP-IDF framework")
    if not config[CONF_URL].startswith("ws://"):
        raise cv.Invalid("url must use ws://; trusted wss:// certificates are not configured")
    if not config[CONF_URL].endswith("/api/nyra/audio"):
        raise cv.Invalid("url must target Home Assistant /api/nyra/audio")
    return config


CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(NyraAudioIngress),
            cv.Required(CONF_MICROPHONE): microphone.microphone_source_schema(
                min_bits_per_sample=16,
                max_bits_per_sample=16,
                min_channels=1,
                max_channels=1,
            ),
            cv.Required(CONF_URL): cv.string_strict,
            cv.Required(CONF_TOKEN): cv.string_strict,
            cv.Required(CONF_SOURCE_ID): cv.string_strict,
            cv.Optional(CONF_LANGUAGE, default="en"): cv.string_strict,
            cv.Optional(CONF_TIMEOUT, default="30s"): cv.positive_time_period_milliseconds,
            cv.Optional(CONF_SPEECH_RMS, default=700): cv.int_range(min=1, max=32767),
            cv.Optional(CONF_CONTINUATION_RMS, default=450): cv.int_range(min=1, max=32767),
            cv.Optional(CONF_SPEECH_ON, default="120ms"): cv.positive_time_period_milliseconds,
            cv.Optional(CONF_TRAILING_SILENCE, default="900ms"): cv.positive_time_period_milliseconds,
            cv.Optional(CONF_NO_SPEECH_TIMEOUT, default="8s"): cv.positive_time_period_milliseconds,
            cv.Optional(CONF_MAX_CAPTURE_DURATION, default="15s"): cv.positive_time_period_milliseconds,
            cv.Optional(CONF_ON_ACCEPTED): automation.validate_automation(
                {cv.GenerateID(CONF_TRIGGER_ID): cv.declare_id(AcceptedTrigger)}
            ),
            cv.Optional(CONF_ON_REJECTED): automation.validate_automation(
                {cv.GenerateID(CONF_TRIGGER_ID): cv.declare_id(RejectedTrigger)}
            ),
            cv.Optional(CONF_ON_FAILED): automation.validate_automation(
                {cv.GenerateID(CONF_TRIGGER_ID): cv.declare_id(FailedTrigger)}
            ),
        }
    ).extend(cv.COMPONENT_SCHEMA),
    _validate,
)

FINAL_VALIDATE_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.Required(CONF_MICROPHONE): microphone.final_validate_microphone_source_schema(
                "nyra_audio_ingress", sample_rate=16000
            ),
        },
        extra=cv.ALLOW_EXTRA,
    ),
)


async def to_code(config):
    esp32.add_idf_component(name="espressif/esp_websocket_client", ref="1.7.0")

    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    mic_source = await microphone.microphone_source_to_code(config[CONF_MICROPHONE], passive=True)
    cg.add(var.set_microphone_source(mic_source))
    cg.add(var.set_url(config[CONF_URL]))
    cg.add(var.set_token(config[CONF_TOKEN]))
    cg.add(var.set_source_id(config[CONF_SOURCE_ID]))
    cg.add(var.set_language(config[CONF_LANGUAGE]))
    cg.add(var.set_timeout_ms(config[CONF_TIMEOUT].total_milliseconds))
    cg.add(var.set_speech_rms(config[CONF_SPEECH_RMS]))
    cg.add(var.set_continuation_rms(config[CONF_CONTINUATION_RMS]))
    cg.add(var.set_speech_on_ms(config[CONF_SPEECH_ON].total_milliseconds))
    cg.add(var.set_trailing_silence_ms(config[CONF_TRAILING_SILENCE].total_milliseconds))
    cg.add(var.set_no_speech_timeout_ms(config[CONF_NO_SPEECH_TIMEOUT].total_milliseconds))
    cg.add(var.set_max_capture_duration_ms(config[CONF_MAX_CAPTURE_DURATION].total_milliseconds))

    for conf in config.get(CONF_ON_ACCEPTED, []):
        trigger = cg.new_Pvariable(conf[CONF_TRIGGER_ID], var)
        await automation.build_automation(trigger, [], conf)
    for conf in config.get(CONF_ON_REJECTED, []):
        trigger = cg.new_Pvariable(conf[CONF_TRIGGER_ID], var)
        await automation.build_automation(trigger, [], conf)
    for conf in config.get(CONF_ON_FAILED, []):
        trigger = cg.new_Pvariable(conf[CONF_TRIGGER_ID], var)
        await automation.build_automation(trigger, [], conf)
