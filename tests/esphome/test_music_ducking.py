from pathlib import Path
import subprocess, shutil

ROOT = Path(__file__).resolve().parents[2]


def test_music_ducking_recomputes_from_current_owners_without_volume_restore(tmp_path):
    source = tmp_path / "duck.cpp"
    source.write_text(r"""
#include "esphome/components/nyra_alerts/nyra_alerts.h"
#include <cassert>
int main(){
 assert(nyra::music_duck_db(false,false,false,false)==9);
 assert(nyra::music_duck_db(false,false,false,false,6)==6);
 assert(nyra::music_duck_db(false,false,false,false,200)==20);
 assert(nyra::music_duck_db(true,false,false,false)==30);
 assert(nyra::music_duck_db(false,true,false,false)==20);
 assert(nyra::music_duck_db(false,false,true,false)==60);
 assert(nyra::music_duck_db(false,false,false,true)==60);
 assert(nyra::music_duck_db(true,true,true,true)==60);
 // Voice ending cannot release an alert's ownership; an announcement ending
 // between repeated tones cannot release active alert ownership either.
 assert(nyra::music_duck_db(false,false,true,false)==60);
 assert(nyra::music_duck_db(false,true,false,false)==20);
 assert(nyra::music_duck_db(false,false,false,false)==9);
}
""")
    binary = tmp_path / "duck"
    subprocess.run(
        [
            shutil.which("c++"),
            "-std=c++17",
            "-I",
            str(ROOT),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True)


def test_only_one_ducking_writer_and_no_resume_or_player_volume_restore():
    core = (
        ROOT / "esphome/vendor/waveshare-esp32-s3-audio-va-v1.0.0-core.yaml"
    ).read_text()
    alerts = (ROOT / "esphome/packages/nyra-alerts.yaml").read_text()
    assert "mixer_speaker.apply_ducking:" not in core
    assert alerts.count("mixer_speaker.apply_ducking:") == 1
    assert "id: nyra_update_music_ducking" in alerts
    assert "nyra::music_duck_db" in alerts
