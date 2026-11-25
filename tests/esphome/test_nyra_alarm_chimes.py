import wave

from tests.esphome.test_nyra_intrusion_siren import ROOT, compile_run, load_yaml


def test_alarm_chime_edges_do_not_replay_boot_reconnect_or_duplicates(tmp_path):
    compile_run(tmp_path, r'''
#include "esphome/components/nyra_alerts/nyra_alerts.h"
#include <cassert>
int main() {
 nyra::AlarmStatusChime edge;
 assert(edge.observe("disarmed")==0);
 assert(edge.observe("arming")==0);
 assert(edge.observe("pending")==0);
 assert(edge.observe("armed_away")==1);
 for(auto s:{"armed_away","armed_home","armed_night","armed_vacation","armed_custom_bypass","triggered","disarming"}) assert(edge.observe(s)==0);
 assert(edge.observe("disarmed")==2);
 assert(edge.observe("disarmed")==0);
 edge.reset(); assert(edge.observe("armed_night")==0);
 assert(edge.observe("unavailable")==0);
 assert(edge.observe("disarmed")==0);
 assert(edge.observe("unknown")==0);
 assert(edge.observe("armed_home")==0);
 assert(edge.observe("disarmed")==2);
 nyra::AlarmStatusChime fresh;
 assert(fresh.observe("triggered")==0);
 assert(fresh.observe("disarmed")==2);
 assert(fresh.observe("armed_garbage")==0);
 assert(fresh.observe("armed_away")==0); // invalid state resets trust
}
''')


def test_actual_chime_callback_uses_bounded_wake_interruptible_owner(tmp_path):
    config = load_yaml('esphome/packages/nyra-alarm-status.yaml')
    callbacks = config['text_sensor'][0]['on_value']['then']
    assert len(callbacks) == 2, 'Missing status chime callback'
    callback = callbacks[1]['lambda']
    compile_run(tmp_path, r'''
#include "esphome/components/nyra_alerts/nyra_alerts.h"
#include <cassert>
#define id(x) x
uint32_t millis(){return 123;}
nyra::AlertState nyra_alert;
nyra::AlarmStatusChime nyra_alarm_chime;
std::string nyra_alert_kind,nyra_alert_url,nyra_url_job;
bool nyra_alert_ready=true;
struct Switch { bool state=false; } timer_ringing;
struct Script {int calls=0;void execute(){++calls;}} nyra_alert_begin;
struct Sensor {std::string state;void publish_state(std::string s){state=s;}} nyra_audio_epoch;
std::string to_string(uint32_t n){return std::to_string(n);}
struct VA {int invalidations=0;void invalidate_output(){++invalidations;}} va;
void on_value(std::string x) {
''' + callback + r'''
}
int main() {
 on_value("disarmed"); assert(!nyra_alert.active);
 on_value("armed_away");
 assert(nyra_alert.active && nyra_alert.call && !nyra_alert.protected_audio());
 assert(nyra_alert_kind=="armed" && nyra_alert.limit==2000);
 assert(va.invalidations==1 && nyra_alert_begin.calls==1 && !nyra_alert_ready);
 nyra_alert.wake(); assert(!nyra_alert.active); // same wake path as normal alerts
 on_value("armed_away");assert(nyra_alert_begin.calls==1);
 on_value("disarmed");assert(nyra_alert_kind=="disarmed");
 nyra_alert.playing();nyra_alert.ended();assert(!nyra_alert.active);
 assert(nyra_alert.start_intrusion(0));
 on_value("armed_away");assert(nyra_alert.protected_audio());
 nyra_alert.stop();on_value("armed_away");assert(!nyra_alert.active); // no delayed replay
 timer_ringing.state=true;on_value("disarmed");assert(!nyra_alert.active);
 timer_ringing.state=false;on_value("disarmed");assert(!nyra_alert.active);
 on_value("armed_night"); assert(nyra_alert.active);
 assert(nyra_alert.tick(2123));assert(!nyra_alert.active); // failed audio bounded too
}
''')
    assert 'nyra_alarm_chime).reset()' in str(config['voice_assistant']['on_client_disconnected'])


def test_chime_assets_are_distinct_short_mono_pcm_and_play_once():
    for name, expected in [('armed', 0.12), ('disarmed', 0.38)]:
        with wave.open(str(ROOT / f'esphome/assets/nyra_{name}.wav')) as wav:
            assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 16000)
            assert abs(wav.getnframes()/wav.getframerate()-expected) < .001
    config = load_yaml('esphome/packages/nyra-alerts.yaml')
    begin = next(s for s in config['script'] if s['id']=='nyra_alert_begin')
    call_branch = begin['then'][-1]['if']['then']
    assert 'nyra_armed_sound' in str(call_branch) and 'nyra_disarmed_sound' in str(call_branch)
    assert 'nyra_alert_repeat' not in str(call_branch)
