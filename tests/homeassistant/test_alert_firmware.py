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
  assert(nyra::wake_word_cutoff(178, 0) == 178);
  assert(nyra::wake_word_cutoff(178, 1) == 152);
  assert(nyra::wake_word_cutoff(178, 2) == 126);
  assert(nyra::wake_word_cutoff(30, 2) == 1);
  assert(nyra::wake_word_cutoff(178, 9) == 126);
  struct File {} file;
  struct LegacyPlayer {
    int calls{0};
    void play_file(File *, bool announcement, bool enqueue) { assert(announcement && !enqueue); ++calls; }
  } legacy;
  struct ModernPlayer {
    int calls{0};
    void play_file(const File *, bool announcement, bool enqueue) { assert(announcement && !enqueue); ++calls; }
  } modern;
  nyra::play_asset(&legacy, &file);
  nyra::play_asset(&modern, &file);
  assert(legacy.calls == 1 && modern.calls == 1);
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


def test_one_wake_reaches_listening_on_every_unmuted_audio_path():
    """The busy-audio branch must not consume the wake as a stop-only action."""
    import yaml

    class Loader(yaml.SafeLoader):
        pass

    Loader.add_constructor("!lambda", lambda loader, node: loader.construct_scalar(node))
    core = (ROOT / "esphome/vendor/waveshare-esp32-s3-audio-va-v1.0.0-core.yaml").read_text()
    section = core.split("micro_wake_word:\n", 1)[1].split("\nvoice_assistant:\n", 1)[0]
    actions = yaml.load(section, Loader=Loader)["on_wake_word_detected"][0]["if"]["then"]

    # Explore the automation's actual if/else paths, expanding referenced scripts.
    scripts = yaml.load("script:\n" + core.split("\nscript:\n", 1)[1].split("\ninterval:\n", 1)[0], Loader=Loader)["script"]
    by_id = {script["id"]: script for script in scripts}

    def paths(actions):
        result = [[]]
        for action in actions:
            if "if" in action:
                branch = action["if"]
                def settled(condition):
                    if "and" in condition:
                        values = [settled(item) for item in condition["and"]]
                        return all(values) if None not in values else None
                    if "not" in condition:
                        value = settled(condition["not"])
                        return None if value is None else not value
                    if condition.get("lambda") == "return !id(nyra_alert).active;":
                        return True  # no newer high-priority alert during the cue
                    if "switch.is_off" in condition:
                        return True  # unmuted physical test
                    if "voice_assistant.is_running" in condition or "media_player.is_announcing" in condition:
                        return False  # stop/settle completed successfully
                    return None
                value = settled(branch["condition"])
                alternatives = (paths(branch.get("then", [])) if value is True else
                                paths(branch.get("else", [])) if value is False else
                                paths(branch.get("then", [])) + paths(branch.get("else", [])))
            elif "script.execute" in action:
                call = action["script.execute"]
                name = call if isinstance(call, str) else call["id"]
                # Only expand the wake handoff; unrelated sound/LED scripts are boundaries.
                alternatives = paths(by_id[name]["then"]) if name == "nyra_wake_listen" else [[action]]
            else:
                alternatives = [[action]]
            result = [prefix + suffix for prefix in result for suffix in alternatives]
        return result

    unmuted_paths = paths(actions)
    assert unmuted_paths
    for path in unmuted_paths:
        names = [next(iter(action)) for action in path]
        assert "voice_assistant.start" in names, "wake stopped audio without reopening listening"
        if "voice_assistant.stop" in names:
            assert names.index("voice_assistant.stop") < names.index("voice_assistant.start")


def test_wake_handoff_still_opens_when_old_pipeline_takes_three_seconds_to_stop():
    """Run the handoff's wait/branch actions with HA cancellation arriving at t=3s."""
    import yaml

    class Loader(yaml.SafeLoader):
        pass

    Loader.add_constructor("!lambda", lambda loader, node: loader.construct_scalar(node))
    core = (ROOT / "esphome/vendor/waveshare-esp32-s3-audio-va-v1.0.0-core.yaml").read_text()
    scripts = yaml.load("script:\n" + core.split("\nscript:\n", 1)[1].split("\ninterval:\n", 1)[0], Loader=Loader)["script"]
    script = next(item for item in scripts if item["id"] == "nyra_wake_listen")
    now = 0.0
    observed = []

    def condition(value):
        if "and" in value:
            return all(condition(item) for item in value["and"])
        if "not" in value:
            return not condition(value["not"])
        if "voice_assistant.is_running" in value:
            return now < 3.0
        if "media_player.is_announcing" in value or "switch.is_on" in value:
            return False
        if "switch.is_off" in value:
            return True
        if value.get("lambda") == "return !id(nyra_alert).active;":
            return True
        raise AssertionError(f"unmodeled hardware condition {value}")

    def run(actions):
        nonlocal now
        for action in actions:
            if "wait_until" in action:
                wait = action["wait_until"]
                timeout = wait.get("timeout")
                deadline = float(timeout[:-1]) if timeout else float("inf")
                start = now
                while not condition(wait["condition"]) and now - start < deadline:
                    now += 0.25
            elif "if" in action:
                branch = action["if"]
                run(branch.get("then" if condition(branch["condition"]) else "else", []))
            else:
                observed.append(next(iter(action)))

    run(script["then"])
    assert now >= 3.0
    assert "voice_assistant.start" in observed
