from pathlib import Path
import shutil
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[2]


def compile_run(tmp_path, text):
    source = tmp_path / 'intrusion.cpp'
    source.write_text(text)
    binary = tmp_path / 'intrusion'
    subprocess.run([shutil.which('c++'), '-std=c++17', '-I', str(ROOT), str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)


def load_yaml(path):
    class Loader(yaml.SafeLoader):
        pass
    Loader.add_multi_constructor('!', lambda loader, tag, node: loader.construct_scalar(node))
    return yaml.load((ROOT / path).read_text(), Loader=Loader)


def test_intrusion_episode_and_protected_audio_deadline(tmp_path):
    compile_run(tmp_path, r'''
#include "esphome/components/nyra_alerts/nyra_alerts.h"
#include <cassert>
int main() {
  nyra::IntrusionEpisode episode;
  for (auto s : {"unknown","pending","armed_home","unavailable"}) assert(episode.observe(s)==0);
  assert(episode.observe("triggered")==1);
  assert(episode.observe("triggered")==0);
  assert(episode.observe("unavailable")==0);
  assert(episode.observe("armed_away")==0);
  assert(episode.observe("triggered")==0);
  assert(episode.observe("disarmed")==2);
  assert(episode.observe("disarmed")==0);
  assert(episode.observe("triggered")==1);
  nyra::AlertState audio;
  audio.epoch=17;
  assert(audio.start("timer",17,60000,false,0));
  audio.stop(); // Adapter publishes old STOPPED before taking over.
  assert(audio.state=="STOPPED");
  assert(audio.start_intrusion(0xfffffff0u));
  auto epoch=audio.epoch;auto job=audio.job;
  assert(epoch==18 && audio.protected_audio());
  audio.playing();audio.wake();
  assert(audio.active && audio.epoch==epoch && audio.job==job);
  assert(!audio.start_intrusion(100));
  assert(!audio.start("late",17,60000,true,100));
  assert(!audio.tick(uint32_t(0xfffffff0u+59999u)));
  assert(audio.tick(uint32_t(0xfffffff0u+60000u)));
  assert(!audio.active && !audio.protected_audio());
  assert(audio.state=="COMPLETED");
  audio.wake();assert(audio.epoch==epoch+1);
  assert(audio.start_intrusion(123));audio.stop();
  assert(!audio.protected_audio() && audio.state=="STOPPED");
  assert(audio.start("ordinary",audio.epoch,1000,false,124));
  audio.wake();assert(!audio.active);
}
''')


def test_actual_alarm_callback_preempts_once_and_disarms_during_start(tmp_path):
    config = load_yaml('esphome/packages/nyra-alarm-status.yaml')
    callback = config['text_sensor'][0]['on_value']['then'][0]['lambda']
    compile_run(tmp_path, r'''
#include "esphome/components/nyra_alerts/nyra_alerts.h"
#include "esphome/components/nyra_status_ring/alarm_indicator.h"
#include <cassert>
#define id(x) x
uint32_t millis(){return 123;}
nyra::AlertState nyra_alert;
nyra::IntrusionEpisode nyra_intrusion_episode;
uint8_t nyra_alarm_indicator_state=0;
std::string nyra_alert_kind,nyra_alert_url,nyra_url_job;
bool nyra_alert_ready=true;
struct Script {int calls=0;void execute(){++calls;}} nyra_alert_publish,nyra_alert_begin;
struct Finish {int calls=0;void execute(){++calls;nyra_alert_publish.execute();
 assert(!nyra_alert.active && nyra_alert.state=="STOPPED");}} nyra_alert_finish;
struct Sensor {std::string state;void publish_state(std::string s){state=s;}} nyra_audio_epoch;
std::string to_string(uint32_t n){return std::to_string(n);}
struct VA {int invalidations=0;void invalidate_output(){++invalidations;}} va;
void on_value(std::string x) {
''' + callback + r'''
}
int main(){
 nyra_alert.start("old-timer",0,60000,false,0);
 on_value("triggered");
 assert(nyra_alert.protected_audio() && nyra_alert_kind=="intrusion");
 assert(nyra_alert_finish.calls==1 && nyra_alert_publish.calls==1 && nyra_alert_begin.calls==1);
 assert(va.invalidations>=1 && !nyra_alert_ready);
 auto epoch=nyra_alert.epoch;
 on_value("triggered");on_value("unavailable");on_value("triggered");
 assert(nyra_alert_begin.calls==1 && nyra_alert.epoch==epoch);
 on_value("disarmed");
 assert(!nyra_alert.active && nyra_alert_finish.calls==2);
 on_value("triggered");assert(nyra_alert_begin.calls==2);
 nyra_alert.tick(60123);on_value("triggered");assert(nyra_alert_begin.calls==2);
 on_value("disarmed");on_value("triggered");assert(nyra_alert_begin.calls==3);
}
''')


def test_wake_and_native_audio_paths_are_guarded_for_intrusion():
    core = load_yaml('esphome/vendor/waveshare-esp32-s3-audio-va-v1.0.0-core.yaml')
    start = next(a for a in core['api']['actions'] if a['action']=='start_va')
    assert 'protected_audio()' in str(start['then'])
    wake = core['micro_wake_word']['on_wake_word_detected'][0]['if']['condition']
    assert 'protected_audio()' in str(wake)
    timers = core['voice_assistant']['on_timer_finished'][0]
    assert 'protected_audio()' in str(timers) and 'switch.turn_on' in str(timers)
    play = next(s for s in core['script'] if s['id']=='play_sound')['then'][0]['lambda']
    assert play.index('protected_audio()') < play.index('if (priority)')
    alarm = next(s for s in core['script'] if s['id']=='check_alarm')['then'][0]['lambda']
    assert alarm.index('protected_audio()') < alarm.index('id(alarm_on)')
    ringing = next(s for s in core['switch'] if s.get('id')=='timer_ringing')
    assert 'protected_audio()' in str(ringing['on_turn_off'])
    alerts = load_yaml('esphome/packages/nyra-alerts.yaml')
    command = alerts['text'][0]['set_action'][0]['lambda']
    assert command.index('protected_audio()') < command.index('action == "URL"')
    repeat = next(s for s in alerts['script'] if s['id']=='nyra_alert_repeat')
    assert 'nyra_intrusion_sound' in str(repeat)
    assert any(a['id']=='nyra_intrusion_sound' for a in alerts['audio_file'])
