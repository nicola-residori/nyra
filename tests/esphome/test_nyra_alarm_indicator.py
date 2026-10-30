from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def test_alarm_overlay_and_idle_priority_are_independent_of_battery_pixels(tmp_path):
    source = tmp_path / "alarm.cpp"
    source.write_text(r'''
#include "esphome/components/nyra_status_ring/alarm_indicator.h"
#include <array>
#include <cassert>
#include <string>
using nyra::AlarmIndicatorState;
struct RGB { unsigned r=0,g=0,b=0; };
int main() {
  assert(nyra::alarm_indicator_state("disarmed") == AlarmIndicatorState::DISARMED);
  for (auto s : {"armed_away","armed_home","armed_night","armed_vacation","armed_custom_bypass","pending","triggered"})
    assert(nyra::alarm_indicator_state(s) == AlarmIndicatorState::ARMED);
  for (auto s : {"unknown","unavailable","","garbage"})
    assert(nyra::alarm_indicator_state(s) == AlarmIndicatorState::UNKNOWN);
  assert(nyra::alarm_indicator_state("arming") == AlarmIndicatorState::ARMING);
  std::array<RGB,7> pixels{};
  pixels[6]={0,255,0};pixels[0]={0,255,0};pixels[1]={0,255,0};
  auto draw = [&](int i, unsigned r,unsigned g,unsigned b) { assert(i>=0 && i<7);pixels[i]={r,g,b}; };
  nyra::render_alarm_indicator(7,2,false,AlarmIndicatorState::ARMED,0,draw);
  assert(pixels[3].r==0 && pixels[4].r==0);
  nyra::render_alarm_indicator(7,2,true,AlarmIndicatorState::ARMED,0,draw);
  assert(pixels[3].r==255 && pixels[4].r==255 && pixels[2].r==0 && pixels[5].r==0);
  for(auto i:{0,1,6}) assert(pixels[i].g==255 && pixels[i].r==0);
  nyra::render_alarm_indicator(7,2,true,AlarmIndicatorState::DISARMED,0,draw);
  assert(pixels[3].r==0 && pixels[4].r==0);
  nyra::render_alarm_indicator(7,2,true,AlarmIndicatorState::UNKNOWN,0,draw);
  assert(pixels[3].r>0 && pixels[3].g>0 && pixels[3].b==0);
  nyra::render_alarm_indicator(7,2,true,AlarmIndicatorState::UNKNOWN,1000,draw);
  assert(pixels[3].r==0 && pixels[4].r==0);
  for(int n=0;n<16;++n) for(int count:{2,3}) {
    nyra::render_alarm_indicator(n,count,true,AlarmIndicatorState::ARMED,0,[&](int i,unsigned,unsigned,unsigned){
      assert(i>=0 && i<n);assert(i!=0 && i!=1 && i!=n-1);
    });
  }
  int red_count=0;
  nyra::render_alarm_indicator(7,3,true,AlarmIndicatorState::ARMED,0,[&](int i,unsigned r,unsigned,unsigned){
    assert(i==2 || i==3 || i==4); if(r) ++red_count;
  });
  assert(red_count==3);
  assert(nyra::idle_indicator_eligible(true,true,true,false,false,false,false,false,false,false));
  assert(!nyra::idle_indicator_eligible(false,true,true,false,false,false,false,false,false,false));
  assert(!nyra::idle_indicator_eligible(true,false,true,false,false,false,false,false,false,false));
  assert(!nyra::idle_indicator_eligible(true,true,false,false,false,false,false,false,false,false));
  for(int busy=0;busy<7;++busy) {
    bool b[7]{};b[busy]=true;
    assert(!nyra::idle_indicator_eligible(true,true,true,b[0],b[1],b[2],b[3],b[4],b[5],b[6]));
  }
}
''')
    compiler = shutil.which("c++") or shutil.which("g++")
    assert compiler
    subprocess.run([compiler,"-std=c++17","-I",str(ROOT),str(source),"-o",str(tmp_path/"alarm")],check=True,capture_output=True)
    subprocess.run([str(tmp_path/"alarm")],check=True,capture_output=True)


def test_actual_idle_loop_does_not_replace_a_ringing_alarm_in_a_playback_gap(tmp_path):
    import yaml
    class Loader(yaml.SafeLoader):
        pass
    Loader.add_constructor("!lambda", lambda loader, node: loader.construct_scalar(node))
    package = yaml.load((ROOT/"esphome/packages/nyra-alarm-status.yaml").read_text(), Loader=Loader)
    body = package["interval"][0]["then"][0]["lambda"].replace("${voice_assist_idle_phase_id}", "0").replace("${nyra_idle_indicator_brightness}", "0.2")
    source = tmp_path/"idle.cpp"
    source.write_text(r'''
#include "esphome/components/nyra_status_ring/alarm_indicator.h"
#include <cassert>
#include <string>
#define id(x) x
namespace media_player { enum class MediaPlayerState { IDLE, MEDIA_PLAYER_STATE_ANNOUNCING }; }
struct Connection { bool is_connected() { return true; } } wifi_id, api_id;
struct Script { bool running=false; bool is_running(){return running;} void execute(){} } va,nyra_close_feedback_sequence,flash_ring,control_leds_volume_changed,check_if_timers_active,nyra_wake_listen;
struct { bool active=false; } nyra_alert;
struct { bool state=true; } timer_ringing;
bool nyra_alarm_indicator_enabled=true,nyra_ring_owned=false,nyra_identity_active=false,nyra_speaking_active=false,init_in_progress=false,improv_ble_in_progress=false,is_timer_active=false;
int voice_assistant_phase=0;
struct { media_player::MediaPlayerState state=media_player::MediaPlayerState::IDLE; } external_media_player;
int writes=0;
struct Call { void set_effect(const char *s){assert(std::string(s)=="nyra_battery_gauge");} void set_brightness(float){} void perform(){++writes;} };
struct Ring { struct { bool is_on(){return true;} } remote_values; const char *get_effect_name(){return "Pulse Fast";} Call turn_on(){return {};} } status_ring;
void tick(){
''' + body + r'''
}
int main(){
 tick(); assert(writes==0); // Ringing without ANNOUNCING or countdown is still busy.
 timer_ringing.state=false;tick();assert(writes==1);
 va.running=true;tick();assert(writes==1);
 va.running=false;flash_ring.running=true;tick();assert(writes==1);
 flash_ring.running=false;nyra_wake_listen.running=true;tick();assert(writes==1);
}
''')
    compiler = shutil.which("c++") or shutil.which("g++")
    subprocess.run([compiler,"-std=c++17","-I",str(ROOT),str(source),"-o",str(tmp_path/"idle")],check=True,capture_output=True)
    subprocess.run([str(tmp_path/"idle")],check=True,capture_output=True)
