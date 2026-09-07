from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INCLUDE = ROOT / "esphome/components/nyra_audio_ingress"


def compile_and_run(tmp_path: Path, source: str) -> None:
    program = tmp_path / "vad_test.cpp"
    binary = tmp_path / "vad_test"
    program.write_text(source, encoding="utf-8")
    compiled = subprocess.run(
        ["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(INCLUDE), str(program), "-o", str(binary)],
        capture_output=True,
        text=True,
    )
    assert compiled.returncode == 0, compiled.stderr
    executed = subprocess.run([str(binary)], capture_output=True, text=True)
    assert executed.returncode == 0, executed.stderr


def test_detector_waits_for_speech_and_finishes_after_trailing_silence(tmp_path: Path):
    compile_and_run(
        tmp_path,
        r'''
#include <array>
#include <cassert>
#include "voice_activity_detector.h"

using namespace esphome::nyra_audio_ingress;

int main() {
  std::array<int16_t, 160> silence{};
  std::array<int16_t, 160> speech{};
  speech.fill(1400);
  VoiceActivityDetector vad;
  vad.reset(1000);
  assert(vad.update(silence.data(), silence.size(), 1000) == CaptureDecision::WAITING_FOR_SPEECH);
  assert(vad.update(speech.data(), speech.size(), 1100) == CaptureDecision::WAITING_FOR_SPEECH);
  assert(vad.update(speech.data(), speech.size(), 1230) == CaptureDecision::SPEAKING);
  assert(vad.update(silence.data(), silence.size(), 1500) == CaptureDecision::SPEAKING);
  assert(vad.update(silence.data(), silence.size(), 2200) == CaptureDecision::COMPLETE);
}
''',
    )


def test_detector_has_no_speech_and_maximum_duration_guards(tmp_path: Path):
    compile_and_run(
        tmp_path,
        r'''
#include <array>
#include <cassert>
#include "voice_activity_detector.h"

using namespace esphome::nyra_audio_ingress;

int main() {
  std::array<int16_t, 160> silence{};
  std::array<int16_t, 160> speech{};
  speech.fill(1400);

  VoiceActivityDetector no_speech;
  no_speech.reset(1000);
  assert(no_speech.update(silence.data(), silence.size(), 9001) == CaptureDecision::NO_SPEECH_TIMEOUT);

  VoiceActivityDetector too_long;
  too_long.reset(1000);
  assert(too_long.update(speech.data(), speech.size(), 1000) == CaptureDecision::WAITING_FOR_SPEECH);
  assert(too_long.update(speech.data(), speech.size(), 1130) == CaptureDecision::SPEAKING);
  assert(too_long.update(speech.data(), speech.size(), 16001) == CaptureDecision::MAX_DURATION);
}
''',
    )
