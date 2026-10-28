"""Compile and execute the firmware's platform-independent ownership core."""

from pathlib import Path
import subprocess
import shutil

ROOT = Path(__file__).resolve().parents[2]


def test_firmware_wake_deadline_duplicate_and_stale_epoch(tmp_path):
    source = tmp_path / "test.cpp"
    source.write_text(r"""
#include "esphome/components/nyra_alerts/nyra_alerts.h"
#include <cassert>
#include <string>
int main() {
  nyra::ConversationOutputGate gate;
  int audible = 0;
  assert(!gate.begin()); // A late RUN_START cannot rearm an invalidated request.
  gate.arm(); gate.begin();
  const auto old_token = gate.token();
  gate.invalidate();
  gate.dispatch(old_token, [&]() { ++audible; });
  assert(audible == 0);
  assert(!gate.enabled());
  gate.arm();
  assert(!gate.enabled()); // Old events before the new pipeline starts are rejected.
  gate.begin();
  gate.dispatch(old_token, [&]() { ++audible; });
  assert(audible == 0);
  gate.dispatch(gate.token(), [&]() { ++audible; });
  assert(audible == 1);
  gate.invalidate(); // Alert takeover disables native VA output too.
  gate.dispatch(gate.token(), [&]() { ++audible; });
  assert(audible == 1);
  nyra::AlertState state;
  state.epoch=123;
  assert(state.start("job_a",123,60000,false,100));
  state.playing();
  assert(!state.tick(60099));
  assert(state.tick(60100));
  assert(!state.active && state.state=="COMPLETED");
  assert(!state.start("job_a",123,60000,false,60101));
  assert(state.start("job_b",123,60000,false,60102));
  state.wake();
  assert(!state.active && state.state=="STOPPED");
  assert(!state.start("job_late",123,60000,true,60103));
  assert(state.start("job_c",124,999999,false,60104));
  state.playing();
  assert(state.tick(120104));
  assert(state.start("job_call",124,60000,true,120105));
  state.playing(); state.ended();
  assert(!state.active && state.state=="COMPLETED");
  assert(state.start("job_wrap",124,60000,false,0xfffffff0));
  state.playing(); assert(state.tick(59984));
}
""")
    compiler = shutil.which("c++") or shutil.which("g++")
    assert compiler, "C++ compiler required to verify local firmware interruption"
    subprocess.run(
        [
            compiler,
            "-std=c++17",
            "-I",
            str(ROOT),
            str(source),
            "-o",
            str(tmp_path / "test"),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run([str(tmp_path / "test")], check=True)
