"""Nyra IT V4 worker; embedded verbatim in the standalone Colab notebook."""
import argparse
import collections
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time
import wave

QUANTIZATION_DRIVER = '"""Align only quantization representative data; delegate training/conversion to upstream."""\nimport runpy\nfrom microwakeword import utils\noriginal_convert=utils.convert_saved_model_to_tflite\n\ndef aligned_convert(config,*args,**kwargs):\n    cfg=dict(config)\n    stride=int(cfg[\'stride\']);length=int(cfg[\'spectrogram_length\'])\n    cfg[\'spectrogram_length\']=((length+stride-1)//stride)*stride\n    if cfg[\'spectrogram_length\']!=length:\n        print(\'Quantization representative frames:\',length,\'->\',cfg[\'spectrogram_length\'],flush=True)\n    return original_convert(cfg,*args,**kwargs)\n\nutils.convert_saved_model_to_tflite=aligned_convert\nrunpy.run_module(\'microwakeword.model_train_eval\',run_name=\'__main__\')\n'

PHRASES = {'ehi_nira_it': 'Ehi Nira', 'nira_it': 'Nira'}
MWW_COMMIT = '4665173cd35f1cff9a61e06fc427f124766c488e'
VOICE_REV = '5041a7a49ae5b3a0f30e6837769eb03fdbb231bd'
VOICES = {'paola': 'it/it_IT/paola/medium/it_IT-paola-medium.onnx',
          'riccardo': 'it/it_IT/riccardo/x_low/it_IT-riccardo-x_low.onnx'}
FAMILIES = {f'{v}-{name}': dict(voice=v, length_scale=length, noise_scale=noise, noise_w_scale=.8)
            for v in VOICES for name, length, noise in [('natural',1.,.667),('fast',.9,.667),
                                                       ('slow',1.1,.667),('clear',1.,.55)]}
HARD = ['Nina','Mira','Nera','Gira','Tira','Lira','Mina','Niro','Nura','Vira','Ira','Nino','Mila',
        'Ehi Nina','Ehi Mira','Ehi Nera','Ehi Lina','Ehi Gina','Ehi','Niente','finirà','venire',
        'La mira è precisa','Gira la pagina','Tira la tenda','La sera è tranquilla',
        'Hai visto Nina?','Una lira italiana','Mi gira la testa','Apri la finestra']
# Disjoint templates by split; same hard confusables intentionally recur with fresh TTS.
TEMPLATES = {
 'training': ['Oggi preparo {obj} in cucina.', 'Per favore porta {obj} sul tavolo.',
              'Domani compriamo {obj} al mercato.', 'Hai trovato {obj} nel cassetto?',
              'Questa mattina ho cercato {obj}.','Vorrei parlare di {obj} con te.'],
 'validation': ['Nel pomeriggio sistemeremo {obj}.','La scatola contiene {obj}.',
                'Puoi spostare {obj} vicino alla porta?'],
 'testing': ['Durante la settimana useremo {obj}.','Ho lasciato {obj} accanto al divano.',
             'Mi hanno raccontato una storia su {obj}.']}
OBJECTS = ['il pane','il libro','il telefono','il bicchiere','il giornale','il cappotto',
           'il quaderno','il pacco','il piatto','il cuscino','il calendario','il biglietto',
           'il regalo','il vaso','il computer','il documento','il tavolino','il disegno',
           'il caricatore','il portafoglio','il cestino','il telecomando']
DEFAULT = dict(run_id='nyra-it-v4-001', seed=18473, reserve_gib=8,
               positives={'ehi_nira_it':6000,'nira_it':4000},
               val_positive=300, test_positive=500, train_hard=4000, val_hard=400,test_hard=600,
               train_speech=5000,val_speech=300,test_speech=500,train_noise=1500,
               ambient_validation_minutes=30,ambient_testing_minutes=120,
               training_steps=[25000,20000],batch_size=128,target_faph=.5,min_recall=.85,
               tensor_arena_estimate=100000,author='Nicola')

def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def file_hash(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def save(p,obj):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False));tmp.replace(p)

def load(p):return json.loads(Path(p).read_text())

def select_families(rows,ratings):
    if set(ratings)!=set(r['id'] for r in rows) or any(type(v) is not bool for v in ratings.values()):
        raise ValueError('Valuta tutti i sample con accetta/scarta.')
    result={}
    for phrase in PHRASES:
        groups=collections.defaultdict(list)
        for r in rows:
            if r['phrase']==phrase:groups[r['family']].append(ratings[r['id']])
        result[phrase]=sorted(f for f,votes in groups.items() if votes and all(votes))
        if not result[phrase]:raise ValueError(f'Nessuna famiglia interamente approvata per {PHRASES[phrase]}.')
    return result

def check_approval(payload,approval):
    if approval.get('confirmed') is not True or approval.get('fingerprint')!=digest(payload):
        raise ValueError('Approvazione assente o obsoleta: rifai preview/selezione/conferma.')

def event_times(probs,cutoff,window,dt=.03,refractory=2.,warmup=3.2):
    """Offline event policy: moving mean, strict > cutoff, warmup, fixed refractory.

    Not a bit-exact ESPHome simulator (firmware cool-off is data dependent).
    """
    times=[];buf=collections.deque(maxlen=window);last=-math.inf
    for i,p in enumerate(probs):
        buf.append(float(p));t=(i+1)*dt
        if len(buf)==window and t>=warmup and sum(buf)>cutoff*window+1e-12 and t-last>=refractory-1e-9:
            times.append(round(t,6));last=t
    return times

def merge_events(a,b,refractory=2.):
    out=[]
    for t in sorted(a+b):
        if not out or t-out[-1]>=refractory-1e-9:out.append(t)
    return out

def evaluation_variants(audio,kind,seed):
    """Deterministic synthetic conditions; derivatives stay within their source split."""
    import numpy as np
    if kind!='positive':return [('original',audio)]
    rng=np.random.default_rng(seed)
    a=audio.astype(np.float32)/32768
    noise=rng.normal(0,1,len(a)).astype(np.float32)
    rms=float(np.sqrt(np.mean(a*a)))
    noise=noise/max(float(np.sqrt(np.mean(noise*noise))),1e-8)*rms/(10**(8/20))
    echo=a.copy();delay=1600
    if len(a)>delay:echo[delay:]+=.3*a[:-delay]
    def pcm(x):return np.clip(x*32767,-32768,32767).astype(np.int16)
    return [('clean',audio),('quiet',pcm(a*.15)),('noise_snr8',pcm(a+noise)),('echo',pcm(echo*.7))]


def recall(rows,phrase,cutoff,window):
    positives=[r for r in rows if r['kind']=='positive' and r['phrase']==phrase]
    if not positives:raise ValueError('Mancano positivi per la valutazione.')
    # 4 s pre-roll; accept only within the annotated utterance interval + 1 s tail.
    return sum(any(r.get('start',4.)<=t<=r.get('end',100.)+1.
                   for t in event_times(r['probs'],cutoff,window)) for r in positives)/len(positives)

def choose_operating_point(rows,phrase,target_faph=.5,min_recall=.85):
    if any(r['split']!='validation' for r in rows):raise ValueError('Calibrazione ammessa solo su validation.')
    ambient=[r for r in rows if r['kind']=='ambient']
    hours=sum(r['duration'] for r in ambient)/3600
    if not hours:raise ValueError('Manca esposizione ambient validation.')
    grid=[]
    for window,cutoff_int in itertools.product([3,5,7],[128,153,179,191,204,217,230,235,240,245,250,253]):
        cutoff=cutoff_int/255
        tp=recall(rows,phrase,cutoff,window)
        events=sum(len(event_times(r['probs'],cutoff,window)) for r in ambient)
        hard=[r for r in rows if r['kind']=='hard']
        hard_fpr=sum(bool(event_times(r['probs'],cutoff,window)) for r in hard)/max(1,len(hard))
        grid.append(dict(cutoff=cutoff,window=window,recall=tp,faph=events/hours,
                         hard_fpr=hard_fpr,validation_hours=hours,
                         feasible=tp>=min_recall and events/hours<=target_faph))
    good=[r for r in grid if r['feasible']]
    best=max(good,key=lambda r:(r['recall'],-r['hard_fpr'],-r['faph'],r['cutoff'],-r['window'])) if good else min(grid,key=lambda r:(r['faph'],r['hard_fpr'],-r['recall']))
    return dict(best,grid=grid)

class Run:
    def __init__(self,root):
        self.root=Path(root);self.cfg=load(self.root/'config.json')
        self.rng=random.Random(self.cfg['seed']);self.voices={}
        self.cfg_fingerprint=digest(dict(config=self.cfg,families=FAMILIES,phrases=PHRASES,
                                         mww=MWW_COMMIT,voices=VOICES,voice_rev=VOICE_REV,worker=file_hash(__file__)))
    def guard(self,extra=0,label='operazione'):
        free=shutil.disk_usage(self.root).free/2**30
        if free<self.cfg['reserve_gib']+extra:
            raise RuntimeError(f'{label}: liberi {free:.1f} GiB, richiesti {extra+self.cfg["reserve_gib"]:.1f}. Riduci profilo e rifai preview con nuovo run_id.')
    def payload(self):
        data=load(self.root/'preview.json')
        if data['config_fingerprint']!=self.cfg_fingerprint:raise ValueError('Configurazione cambiata: rigenera preview.')
        for row in data['rows']:
            if file_hash(self.root/row['path'])!=row['sha256']:raise ValueError('Audio preview modificato: rifai preview.')
        return data
    def approved(self):
        data=self.payload();a=load(self.root/'approval.json');check_approval(data,a)
        chosen=select_families(data['rows'],a['ratings'])
        if chosen!=a['selected']:raise ValueError('Selezione alterata.')
        return chosen
    def voice(self,name):
        if name not in self.voices:
            from piper import PiperVoice
            self.voices[name]=PiperVoice.load(str(self.root/'voices'/Path(VOICES[name]).name),use_cuda=False)
        return self.voices[name]
    def synth(self,text,family):
        import numpy as np
        from scipy.signal import resample_poly
        from piper import SynthesisConfig
        f=FAMILIES[family];voice=self.voice(f['voice'])
        conf=SynthesisConfig(length_scale=f['length_scale'],noise_scale=f['noise_scale'],
                             noise_w_scale=f['noise_w_scale'],normalize_audio=True)
        chunks=list(voice.synthesize(text,syn_config=conf))
        if not chunks:raise RuntimeError('TTS non ha prodotto audio.')
        a=np.concatenate([c.audio_float_array for c in chunks]);sr=chunks[0].sample_rate
        a=resample_poly(a,16000//math.gcd(sr,16000),sr//math.gcd(sr,16000)).astype(np.float32)
        if not np.isfinite(a).all() or np.max(np.abs(a))<.001:raise RuntimeError('Sample vuoto o non valido.')
        # Remove digital boundary silence only; never concatenate Ehi and Nira.
        active=np.flatnonzero(np.abs(a)>.005)
        if not len(active):raise RuntimeError('TTS silenzioso.')
        a=a[max(0,active[0]-800):min(len(a),active[-1]+801)]
        return np.clip(a,-1,1)
    def write_wav(self,path,a):
        import numpy as np
        from scipy.io.wavfile import write
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        write(str(path),16000,np.clip(a*32767,-32768,32767).astype(np.int16))
    def ensure_voices(self):
        from huggingface_hub import hf_hub_download
        self.guard(2,'download voci')
        for name,remote in VOICES.items():
            for suffix in ['', '.json']:
                src=hf_hub_download(repo_id='rhasspy/piper-voices',filename=remote+suffix,
                                   revision=VOICE_REV,local_dir=str(self.root/'voice_download'))
                dst=self.root/'voices'/(Path(remote).name+suffix);dst.parent.mkdir(exist_ok=True)
                shutil.copy2(src,dst)
            card=hf_hub_download(repo_id='rhasspy/piper-voices',filename=str(Path(remote).parent/'MODEL_CARD'),
                                 revision=VOICE_REV,local_dir=str(self.root/'voice_download'))
            shutil.copy2(card,self.root/'voices'/f'{name}_MODEL_CARD.txt')
    def preview(self):
        (self.root/'approval.json').unlink(missing_ok=True)
        self.ensure_voices()
        rows=[]
        for phrase,text in PHRASES.items():
            for family in FAMILIES:
                for j in range(2):
                    a=self.synth(text,family)
                    if len(a)/16000>1.8:raise RuntimeError(f'{text}/{family}: durata >1.8s; non approvare campioni tagliati.')
                    id_=f'{phrase}__{family}__{j}'
                    p=Path('preview')/(id_+'.wav');self.write_wav(self.root/p,a)
                    rows.append(dict(id=id_,phrase=phrase,family=family,path=str(p),sha256=file_hash(self.root/p),duration=len(a)/16000))
                    print('Preview',id_,flush=True)
        save(self.root/'preview.json',dict(config_fingerprint=self.cfg_fingerprint,rows=rows))
    def noise(self,seconds,seed):
        import numpy as np
        from scipy.signal import lfilter
        g=np.random.default_rng(seed);n=int(seconds*16000)
        a=g.normal(0,1,n)
        mode=seed%5
        if mode==0:a=lfilter([.1],[1,-.9],a)
        elif mode==1:a=np.diff(a,prepend=0)
        elif mode==2:
            t=np.arange(n)/16000;a=.1*a+np.sin(2*np.pi*(50+seed%100)*t)
        elif mode==3:
            a*=.03
            for _ in range(12):
                i=int(g.integers(0,max(1,n-2000)));a[i:i+2000]+=np.exp(-np.arange(min(2000,n-i))/180)*g.normal()
        a=a/(np.max(np.abs(a))+1e-8)*g.uniform(.01,.35)
        return a.astype(np.float32)
    def generate(self):
        import numpy as np
        chosen=self.approved()
        self.ensure_voices()
        if (self.root/'dataset.json').exists():
            d=load(self.root/'dataset.json')
            if d['approval_fingerprint']!=digest(load(self.root/'approval.json')):raise ValueError('Dataset precedente con altra approvazione: usa nuovo run_id.')
            print('Dataset già completo: riutilizzato.');return
        # Transactional rebuild after interruptions, only THIS run's working data.
        for d in ['audio','features','scores','models']:
            shutil.rmtree(self.root/d,ignore_errors=True)
        npos=sum(self.cfg['positives'].values())+2*(self.cfg['val_positive']+self.cfg['test_positive'])
        nneg=sum(self.cfg[k] for k in ['train_hard','val_hard','test_hard','train_speech','val_speech','test_speech','train_noise'])
        wav_gib=((npos+nneg)*5*32000+(self.cfg['ambient_validation_minutes']+self.cfg['ambient_testing_minutes'])*60*32000)/2**30
        self.guard(wav_gib*1.3+3,'stima WAV completa')
        rows=[];seen={r['sha256'] for r in self.payload()['rows']}
        def add(kind,split,phrase,family,text,a):
            if len(rows)%100==0:self.guard(1,f'generazione {len(rows)}');print('WAV',len(rows),flush=True)
            p=Path('audio')/kind/phrase/split/f'{len(rows):07d}.wav'
            self.write_wav(self.root/p,a);h=file_hash(self.root/p)
            if h in seen:raise RuntimeError('Duplicato audio esatto (anche fra split): dataset bloccato. Non riusare la preview.')
            seen.add(h)
            rows.append(dict(id=len(rows),kind=kind,split=split,phrase=phrase,family=family,text=text,
                             path=str(p),sha256=h,duration=len(a)/16000))
        for phrase,text in PHRASES.items():
            for split,n in [('training',self.cfg['positives'][phrase]),('validation',self.cfg['val_positive']),('testing',self.cfg['test_positive'])]:
                for i in range(n):
                    family=chosen[phrase][i%len(chosen[phrase])];a=self.synth(text,family)
                    if len(a)/16000>1.8:raise RuntimeError(f'Sample positivo troppo lungo: {phrase}/{family}. Rivedi famiglie.')
                    add('positive',split,phrase,family,text,a)
        all_families=sorted(set(sum(chosen.values(),[])))
        for kind in ['hard','speech']:
            for split,key in [('training','train'),('validation','val'),('testing','test')]:
                for i in range(self.cfg[f'{key}_{kind}']):
                    text=HARD[i%len(HARD)] if kind=='hard' else self.rng.choice(TEMPLATES[split]).format(obj=self.rng.choice(OBJECTS))
                    # Neither approved wake phrase is ever a negative.
                    assert 'nira' not in text.casefold()
                    fam=self.rng.choice(all_families);a=self.synth(text,fam)
                    add(kind,split,'negative',fam,text,a)
        for i in range(self.cfg['train_noise']):
            add('noise','training','negative','procedural','',self.noise(3.2,self.cfg['seed']+i))
        # Long independent negative streams, not repetitions of training WAVs.
        for split in ['validation','testing']:
            total=60*self.cfg[f'ambient_{split}_minutes'];duration=60
            for stream in range(math.ceil(total/duration)):
                seconds=min(duration,total-stream*duration)
                seed=self.cfg['seed']+(100000 if split=='validation' else 200000)+stream
                rng=random.Random(seed);a=self.noise(seconds,seed)*.08;cursor=.5
                while cursor<seconds-6:
                    text=rng.choice(TEMPLATES[split]).format(obj=rng.choice(OBJECTS))
                    if rng.random()<.2:text=rng.choice(HARD)
                    fam=rng.choice(all_families);utterance=self.synth(text,fam)*rng.uniform(.15,.7)
                    i=int(cursor*16000);length=min(len(utterance),len(a)-i)
                    a[i:i+length]+=utterance[:length];cursor+=length/16000+rng.uniform(.3,1.8)
                add('ambient',split,'negative','mixed','TTS italiano + rumori procedurali',np.clip(a,-1,1))
        save(self.root/'dataset.json',dict(approval_fingerprint=digest(load(self.root/'approval.json')),rows=rows))
        print('Dataset completo',len(rows),'WAV; nessun corpus registrato.',flush=True)
    def dataset(self):
        self.approved();d=load(self.root/'dataset.json')
        if d['approval_fingerprint']!=digest(load(self.root/'approval.json')):raise ValueError('Dataset obsoleto.')
        return d['rows']
    def features(self):
        import numpy as np
        from scipy.io.wavfile import read
        from microwakeword.audio.audio_utils import generate_features_for_clip
        from microwakeword.audio.augmentation import Augmentation
        from mmap_ninja.ragged import RaggedMmap
        rows=self.dataset()
        # Direct WAV iteration avoids datasets.Audio API/codec drift; official augmentation,
        # official microfrontend, official RaggedMmap, no resplitting inside Clips.
        aug=Augmentation(augmentation_duration_s=None,augmentation_probabilities={
            'SevenBandParametricEQ':.2,'TanhDistortion':.1,'PitchShift':.15,
            'BandStopFilter':.1,'AddColorNoise':.45,'Gain':1.,'GainTransition':.25},
            impulse_paths=[],background_paths=[],min_jitter_s=.10,max_jitter_s=.25,
            min_gain_db=-28,max_gain_db=-1)
        for kind,phrase,split in sorted(set((r['kind'],r['phrase'],r['split']) for r in rows)):
            subset=[r for r in rows if (r['kind'],r['phrase'],r['split'])==(kind,phrase,split)]
            source=phrase if kind=='positive' else kind
            outsplit=(split+'_ambient') if kind=='ambient' else split
            out=self.root/'features'/source/outsplit/'wakeword_mmap'
            marker=out.parent/'complete.json'
            fingerprint=digest(dict(rows=subset,config=self.cfg_fingerprint))
            if marker.exists() and load(marker).get('fingerprint')==fingerprint and out.exists():
                print('Feature già complete',source,outsplit);continue
            # Conservative exact shape-based upper bound including mmap overhead and safety.
            seconds=sum((3.2 if kind=='positive' else max(3.2,r['duration'])) for r in subset)
            repeats=2 if split=='training' else 1
            estimate=seconds*100*40*4*repeats/2**30*1.5
            self.guard(estimate+1,f'feature {source}/{outsplit}')
            shutil.rmtree(out,ignore_errors=True);marker.unlink(missing_ok=True);out.parent.mkdir(parents=True,exist_ok=True)
            def iterator():
                for r in subset:
                    sr,a=read(self.root/r['path']);assert sr==16000 and a.dtype==np.int16
                    for _ in range(repeats):
                        if kind=='ambient':b=a
                        elif split=='training':
                            # Same acoustic augmentation for positives and negatives; no class cue.
                            b=aug.augment_clip(a.astype(np.float32)/32768)
                            b=continuous_context(b,self.cfg['seed']+r['id']*7919+_,tail_s=.15)
                        else:
                            # Explicit deterministic right alignment, untouched pronunciation.
                            b=continuous_context(a,self.cfg['seed']+r['id']*7919,tail_s=.15)
                        x=generate_features_for_clip(b,step_ms=10)
                        if x.ndim!=2 or x.shape[1]!=40 or not np.isfinite(x).all():raise RuntimeError('Feature non valide.')
                        yield x
            RaggedMmap.from_generator(out_dir=str(out),sample_generator=iterator(),batch_size=64,verbose=True)
            save(marker,dict(fingerprint=fingerprint,count=len(subset)*repeats))
            self.guard(0,'fine estrazione')
        print('Features condivise: negativi una sola copia per i due modelli.')
    def train_config(self,phrase):
        def src(name,truth,weight,penalty=1.,strategy='random'):
            return dict(features_dir=str(self.root/'features'/name),truth=truth,sampling_weight=weight,
                        penalty_weight=penalty,truncation_strategy=strategy,type='mmap')
        return dict(window_step_ms=10,train_dir=str(self.root/'models'/phrase),
                    features=[src(phrase,True,8.,2.,'truncate_start'),src('hard',False,10.,4.),
                              src('speech',False,12.,2.),src('noise',False,5.),src('continuous',False,12.,2.),src('ambient',False,0.,1.,'split')],
                    training_steps=self.cfg['training_steps'],positive_class_weight=[2,2],
                    negative_class_weight=[20,30],learning_rates=[.001,.0001],batch_size=self.cfg['batch_size'],
                    time_mask_max_size=[5,5],time_mask_count=[1,1],freq_mask_max_size=[3,3],freq_mask_count=[1,1],
                    eval_step_interval=500,clip_duration_ms=1800,target_minimization=self.cfg['target_faph'],
                    minimization_metric='ambient_false_positives_per_hour',maximization_metric='average_viable_recall')
    def train(self,phrase,resume=False):
        import yaml
        self.dataset();self.guard(4,'training '+phrase)
        cfg=self.train_config(phrase);p=self.root/f'{phrase}_training.yaml'
        p.write_text(yaml.safe_dump(cfg,sort_keys=False))
        model_dir=self.root/'models'/phrase;done=model_dir/'complete.json'
        if done.exists() and load(done).get('config')==digest(cfg):
            print('Training già completato:',phrase);return
        if model_dir.exists() and any(model_dir.iterdir()) and not resume:
            raise RuntimeError('Training interrotto presente. Per riprendere riesegui la cella con RESUME=True; il calendario training ufficiale riparte. Non cancelliamo checkpoint.')
        # The official trainer rejects a precreated log directory unless restore is enabled.
        # Fresh-run/interruption protection above remains in effect; upstream restores
        # a checkpoint only when one exists.
        model_dir.mkdir(parents=True,exist_ok=True)
        cmd=[sys.executable,'-u','-c',QUANTIZATION_DRIVER,'--training_config',str(p),
             '--train','1','--restore_checkpoint','1','--test_tflite_streaming_quantized','1','--use_weights','best_weights',
             'mixednet','--pointwise_filters','64,64,64,64','--repeat_in_block','1,1,1,1',
             '--mixconv_kernel_sizes','[5], [7,11], [9,15], [23]','--residual_connection','0,0,0,0',
             '--first_conv_filters','32','--first_conv_kernel_size','5','--stride','3']
        env=os.environ.copy();env['XLA_FLAGS']='--xla_gpu_autotune_level=0';env['PYTHONUNBUFFERED']='1'
        log=model_dir/'training.log';last=time.monotonic()
        with log.open('w') as f:
            proc=subprocess.Popen(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
            for line in proc.stdout:
                print(line,end='',flush=True);f.write(line);f.flush()
                if time.monotonic()-last>300:self.backup(light=True);last=time.monotonic()
            code=proc.wait()
        self.backup(light=True)
        if code:raise RuntimeError(f'Training {phrase} fallito, codice {code}. Leggi {log}. Non è stato alterato il codice ufficiale.')
        self.model_path(phrase)
        save(done,dict(config=digest(cfg)));self.backup(light=True)
    def model_path(self,phrase):
        p=self.root/'models'/phrase/'tflite_stream_state_internal_quant'/'stream_state_internal_quant.tflite'
        if not p.is_file():raise FileNotFoundError(p)
        return p
    def score(self,split):
        import numpy as np
        from scipy.io.wavfile import read
        from microwakeword.audio.audio_utils import generate_features_for_clip
        from microwakeword.inference import Model
        rows=[r for r in self.dataset() if r['split']==split]
        # Noise training rows are never included in evaluation.
        for phrase in PHRASES:
            model_path=self.model_path(phrase);out=self.root/'scores'/f'{phrase}_{split}.json'
            fp=digest(dict(model=file_hash(model_path),rows=rows,policy='continuous-v6-21conditions'))
            if out.exists() and load(out)['fingerprint']==fp:print('Score già presenti',out);continue
            results=[];start=time.monotonic()
            for i,r in enumerate(rows):
                sr,a=read(self.root/r['path']);assert sr==16000
                for condition,variant in evaluation_variants(a,r['kind'],self.cfg['seed']+r['id']):
                    # Fresh interpreter and fresh frontend for each INDEPENDENT stream/clip.
                    model=Model(str(model_path),stride=3)
                    assert model.input_details[0]['dtype']==np.int8 and model.output_details[0]['dtype']==np.uint8
                    assert list(model.input_details[0]['shape'])==[1,3,40]
                    assert list(model.output_details[0]['shape'])==[1,1]
                    padded=variant # 4 s warm-up, 1 s detection tail.
                    x=generate_features_for_clip(padded,step_ms=10)
                    probs=list(map(float,model.predict_spectrogram(x)))
                    results.append(dict(r,**({'duration':len(padded)/16000} if r['kind']!='positive' else {}),id=f"{r['id']}:{condition}",condition=condition,probs=probs,start=4.,end=4.+r['duration']))
                    del model
                if i%50==0:print(phrase,split,i,'/',len(rows),'elapsed',round(time.monotonic()-start),'s',flush=True)
            save(out,dict(fingerprint=fp,model_hash=file_hash(model_path),rows=results))
        self.backup(light=True)
    def calibrate(self):
        ops={}
        for phrase in PHRASES:
            data=load(self.root/'scores'/f'{phrase}_validation.json')
            if data['model_hash']!=file_hash(self.model_path(phrase)):raise ValueError('Score validation obsoleti.')
            ops[phrase]=choose_operating_point(data['rows'],phrase,self.cfg['target_faph'],self.cfg['min_recall'])
            ops[phrase]['model_hash']=data['model_hash']
            ops[phrase]['validation_fingerprint']=data['fingerprint']
        save(self.root/'operating_points.json',ops)
        print(json.dumps({k:{kk:vv for kk,vv in v.items() if kk!='grid'} for k,v in ops.items()},indent=2))
        self.backup(light=True)
    def report(self):
        from scipy.stats import chi2
        self.dataset();ops=load(self.root/'operating_points.json');allrows={};report={}
        for phrase in PHRASES:
            data=load(self.root/'scores'/f'{phrase}_testing.json')
            if data['model_hash']!=file_hash(self.model_path(phrase)):raise ValueError('Score test obsoleti.')
            rows=data['rows'];allrows[phrase]=rows;o=ops[phrase]
            if o['model_hash']!=data['model_hash']:raise ValueError('Calibrazione obsoleta.')
            cut=o['cutoff'];win=o['window']
            amb=[r for r in rows if r['kind']=='ambient'];h=sum(r['duration'] for r in amb)/3600
            counts=sum(len(event_times(r['probs'],cut,win)) for r in amb)
            hard=[r for r in rows if r['kind']=='hard'];speech=[r for r in rows if r['kind']=='speech']
            report[phrase]=dict(operating_point={k:v for k,v in o.items() if k!='grid'},
                recall_by_phrase={p:recall(rows,p,cut,win) for p in PHRASES},
                recall_by_condition={c:{p:recall([r for r in rows if r.get('condition')==c],p,cut,win) for p in PHRASES}
                                     for c in EVAL_CONDITIONS},
                hard_false_clip_fraction=sum(bool(event_times(r['probs'],cut,win)) for r in hard)/len(hard),
                speech_false_clip_fraction=sum(bool(event_times(r['probs'],cut,win)) for r in speech)/len(speech),
                ambient_events=counts,ambient_hours=h,synthetic_faph=counts/h,
                poisson_upper95_faph=float(.5*chi2.ppf(.95,2*(counts+1))/h),
                model_bytes=self.model_path(phrase).stat().st_size)
        first,second=list(PHRASES);a={r['id']:r for r in allrows[first]};b={r['id']:r for r in allrows[second]}
        assert a.keys()==b.keys()
        def events(r,p):return event_times(r['probs'],ops[p]['cutoff'],ops[p]['window'])
        n=0;hours=0.;union_tp=collections.Counter();totals=collections.Counter();union_hard=0;nhard=0
        for id_,r in a.items():
            ev=merge_events(events(r,first),events(b[id_],second))
            if r['kind']=='ambient':n+=len(ev);hours+=r['duration']/3600
            if r['kind']=='positive':
                totals[r['phrase']]+=1
                union_tp[r['phrase']]+=any(r['start']<=t<=r['end']+1. for t in ev)
            if r['kind']=='hard':union_hard+=bool(ev);nhard+=1
        report['union']=dict(synthetic_faph=n/hours,events=n,hours=hours,
                            poisson_upper95_faph=float(.5*chi2.ppf(.95,2*(n+1))/hours),
                            recall_by_phrase={p:union_tp[p]/totals[p] for p in PHRASES},hard_false_clip_fraction=union_hard/nhard)
        report['operating_points_hash']=digest(ops)
        report['model_hashes']={p:file_hash(self.model_path(p)) for p in PHRASES}
        report['limitations']=['Solo due voci TTS; nessun test con parlanti umani o audio domestico.',
            'Gli split separano waveform, seed e template di frasi; non separano il modello TTS né tutti i fonemi.',
            'FP/h sintetici: non rappresentano la distribuzione domestica; limite Poisson solo descrittivo e sotto ipotesi di eventi indipendenti.',
            'Eventi offline: media mobile e refractory 2 s, warm-up 3.2 s; non replica esattamente cool-off ESPHome, VAD, stop/restart e scheduling.',
            'Nira dentro Ehi Nira può attivare il modello corto: risposta positiva prevista, non falso positivo.',
            'Il riconoscitore lungo può imparare il suffisso Nira: recall incrociata riportata, nessuna promessa di isolamento lessicale.',
            'Arena TFLM, RAM complessiva e latenza sul Waveshare ESP32-S3 richiedono compilazione e test sul dispositivo.']
        report['test_passed_descriptively']=all(report[p]['recall_by_phrase'][p]>=self.cfg['min_recall'] for p in PHRASES) and report['union']['synthetic_faph']<=self.cfg['target_faph']
        save(self.root/'evaluation.json',report);print(json.dumps(report,indent=2,ensure_ascii=False));self.backup(light=True)
    def export(self):
        self.dataset();ops=load(self.root/'operating_points.json');report=load(self.root/'evaluation.json')
        if report['operating_points_hash']!=digest(ops) or report['model_hashes']!={p:file_hash(self.model_path(p)) for p in PHRASES}:
            raise ValueError('Report non corrispondente a modelli/soglie attuali: rivaluta.')
        if not all(o['feasible'] for o in ops.values()):
            raise RuntimeError('Nessuna coppia soglie/recall accettabile su validation. Report salvato; rivedi dati o training, senza calibrare sul test.')
        out=self.root/'export';out.mkdir(exist_ok=True)
        resources={}
        for phrase,text in PHRASES.items():
            src=self.model_path(phrase);shutil.copy2(src,out/f'{phrase}.tflite');op=ops[phrase]
            manifest=dict(type='micro',wake_word=text,author=self.cfg['author'],model=f'{phrase}.tflite',
                          trained_languages=['it'],version=2,micro=dict(probability_cutoff=op['cutoff'],
                          sliding_window_size=op['window'],feature_step_size=10,
                          tensor_arena_size=self.cfg['tensor_arena_estimate'],minimum_esphome_version='2024.7.0'))
            save(out/f'{phrase}.json',manifest)
            resources[phrase]=dict(tflite_bytes=src.stat().st_size,arena_estimate=self.cfg['tensor_arena_estimate'],
                                    variable_arena_reference=1024,arena_measured=False)
        resources['notes']='Due arene + overhead/framework/audio; dimensione .tflite non misura RAM. Budget arena candidato 2 x 100000 B + variabili, da misurare. Test prima lungo da solo, poi corto da solo, poi entrambi.'
        save(out/'resources.json',resources)
        for name in ['config.json','approval.json','preview.json','evaluation.json','operating_points.json','environment.txt','source_provenance.json']:
            p=self.root/name
            if p.exists():shutil.copy2(p,out/name)
        for p in self.root.glob('*_training.yaml'):shutil.copy2(p,out/p.name)
        for p in (self.root/'voices').glob('*MODEL_CARD*'):shutil.copy2(p,out/p.name)
        yaml_text='''# Merge into EXISTING Nyra package; replaces the two model overrides.
# Keep existing microphone, mww ID and on_wake_word_detected automation.
micro_wake_word:
  models:
    - id: !extend alexa
      model: /config/esphome/models/ehi_nira_it.json
    - id: !extend okay_nabu
      model: /config/esphome/models/nira_it.json
# Enable BOTH models explicitly in an existing on_boot (after priority -100):
# - micro_wake_word.enable_model: alexa
# - micro_wake_word.enable_model: okay_nabu
# Existing model enabled states can persist in flash; verify both in HA/logs.
'''
        (out/'nyra-existing-package.yaml').write_text(yaml_text)
        (out/'README.txt').write_text('MODELLI CANDIDATI, SOLO TEST SINTETICI. Leggere evaluation.json e resources.json.\n'
            'Manifest schema 2. Copiare ogni coppia JSON/TFLite nello stesso percorso.\n'
            'Arena stimata, non misurata; compilare ESPHome e verificare allocazioni e latenza sul dispositivo.\n'
            'Non sostituire alla cieca il file completo dello speaker. YAML fornito per i due !extend esistenti.\n'
            'Il test finale non viene usato per scegliere soglie: eventuali fallimenti richiedono nuovi dati/run.\n')
        shutil.make_archive(str(self.root/'nyra_it_v6_candidates'),'zip',out)
        self.backup(light=True);print('ZIP candidati:',self.root/'nyra_it_v5_candidates.zip')
    def backup(self,light=True):
        target=os.environ.get('NYRA_BACKUP')
        if not target:return
        dst=Path(target)/self.cfg['run_id'];dst.mkdir(parents=True,exist_ok=True)
        # No audio/features in Drive; reproducibility records + weights/checkpoints/reports.
        for p in self.root.glob('*'):
            if p.is_file():shutil.copy2(p,dst/p.name)
        for name in ['preview','models','export']:
            src=self.root/name
            if src.exists():shutil.copytree(src,dst/name,dirs_exist_ok=True)
        print('Backup Drive:',dst,flush=True)

# V5 dataset and evaluation extension. Official frontend/trainer are unchanged.
VOICES = dict(VOICES, serena='it/it_IT/serena/medium/it_IT-serena-medium.onnx')
TEXT_VARIANTS = {
 'ehi_nira_it': {'spaced':'Ehi Nira','ei_spaced':'Ei Nira','joined_ehi':'Ehinira','joined_ei':'Einira','pause':'Ehi, Nira'},
 'nira_it': {'solo':'Nira','calling':'Nira!','question':'Nira?'}}
FAMILIES = {
 f'{voice}-{style}-{phrase}-{variant}':dict(voice=voice,length_scale=length,noise_scale=.667,noise_w_scale=.8,
     phrase=phrase,variant=variant,text=text,style=style)
 for voice in VOICES for style,length in [('natural',1.),('fast',.82),('slow',1.16)]
 for phrase,variants in TEXT_VARIANTS.items() for variant,text in variants.items()}
ACOUSTIC_PROFILES = ('clean','quiet','off_axis_mild','off_axis_strong','reflections','noise_snr10','off_axis_noise')
HARD = HARD + ['Ei Nina','Einina','Ehimira','Ehinina','Ehi gira','Ei Mira','Mira!','Nina?']
DEFAULT = dict(DEFAULT,run_id='nyra-it-v5-003-coverage',seed=310301,
 positives={'ehi_nira_it':18000,'nira_it':12000},val_positive=600,test_positive=900,
 train_hard=8000,train_speech=8000,train_noise=2000,train_continuous=1800,
 ambient_validation_minutes=120,ambient_testing_minutes=240,training_steps=[35000,25000],
 acoustic_profiles=list(ACOUSTIC_PROFILES))


def acoustic(audio,profile,seed):
    """Approximate digital attenuation/off-axis/reflection effects, not calibrated room IRs."""
    import numpy as np
    from scipy.signal import butter,sosfilt,fftconvolve
    a=np.asarray(audio,dtype=np.float32).copy();rng=np.random.default_rng(seed)
    if profile not in ACOUSTIC_PROFILES:raise ValueError('Profilo acustico sconosciuto: '+profile)
    if profile=='clean':return np.clip(a,-1,1)
    if profile in ('off_axis_mild','off_axis_strong','off_axis_noise'):
        fc=rng.uniform(2500,4200) if profile=='off_axis_mild' else rng.uniform(1000,2200)
        a=sosfilt(butter(2,fc,fs=16000,output='sos'),a).astype(np.float32)
        a*=10**(rng.uniform(-6,-2)/20)
    if profile in ('quiet','off_axis_noise'):a*=10**(rng.uniform(-22,-8)/20)
    if profile=='reflections':
        impulse=np.zeros(7200,dtype=np.float32);impulse[0]=1
        for _ in range(10):
            d=int(rng.uniform(.018,.4)*16000)
            impulse[d]+=rng.uniform(-.35,.35)*np.exp(-d/(16000*.17))
        a=fftconvolve(a,impulse)[:len(a)].astype(np.float32)
    if profile in ('noise_snr10','off_axis_noise'):
        snr=10 if profile=='noise_snr10' else rng.uniform(5,15)
        n=rng.normal(0,1,len(a)).astype(np.float32)
        rms=float(np.sqrt(np.mean(a*a)))
        n*=rms/(max(float(np.sqrt(np.mean(n*n))),1e-8)*10**(snr/20))
        a+=n
    peak=float(np.max(np.abs(a))) if len(a) else 0.
    if peak>1:a/=peak*1.001
    if not np.isfinite(a).all():raise ValueError('Trasformazione non finita')
    return a.astype(np.float32)


def select_families(rows,ratings):
    if set(ratings)!=set(r['id'] for r in rows) or any(type(v) is not bool for v in ratings.values()):
        raise ValueError('Valuta tutti i sample: nessuna accettazione automatica.')
    selected={}
    for phrase in PHRASES:
        groups=collections.defaultdict(list)
        for r in rows:
            if r['phrase']==phrase and r.get('preview_kind','tts')=='tts':groups[r['family']].append(ratings[r['id']])
        selected[phrase]=sorted(k for k,vs in groups.items() if vs and all(vs))
        if not selected[phrase]:raise ValueError('Nessuna famiglia approvata per '+phrase)
    return selected


_original_choose_operating_point=choose_operating_point

def choose_operating_point(rows,phrase,target_faph=.5,min_recall=.85):
    op=_original_choose_operating_point(rows,phrase,target_faph,min_recall)
    variants=sorted({r.get('variant','canonical') for r in rows if r['kind']=='positive' and r['phrase']==phrase})
    for item in op['grid']:
        item['recall_by_variant']={v:recall([r for r in rows if r.get('variant','canonical')==v],phrase,item['cutoff'],item['window']) for v in variants}
        item['feasible']=item['feasible'] and all(x>=.75 for x in item['recall_by_variant'].values())
    good=[r for r in op['grid'] if r['feasible']]
    key=lambda r:(r['recall'],-r['hard_fpr'],-r['faph'],r['cutoff'],-r['window'])
    best=max(good,key=key) if good else min(op['grid'],key=lambda r:(r['faph'],-min(r['recall_by_variant'].values()),-r['recall']))
    return dict(best,grid=op['grid'])


_original_evaluation_variants=evaluation_variants

def evaluation_variants(audio,kind,seed):
    if kind!='positive':return [('original',audio)]
    import numpy as np
    # Conditions are applied to the same independent TTS source, never new speakers.
    a=audio.astype(np.float32)/32768
    return [(p,np.clip(acoustic(a,p,seed+i*1301)*32767,-32768,32767).astype(np.int16)) for i,p in enumerate(ACTIVE_EVALUATION_PROFILES)]


ACTIVE_EVALUATION_PROFILES=ACOUSTIC_PROFILES

_BaseRun=Run

class Run(_BaseRun):
    def preview(self):
        (self.root/'approval.json').unlink(missing_ok=True);self.ensure_voices();rows=[];unavailable=[]
        for family,f in FAMILIES.items():
            a=self.synth(f['text'],family)
            if len(a)>28800:
                unavailable.append(dict(family=family,duration=len(a)/16000));continue
            id_=family;p=Path('preview')/(id_+'.wav');self.write_wav(self.root/p,a)
            rows.append(dict(id=id_,phrase=f['phrase'],family=family,variant=f['variant'],text=f['text'],preview_kind='tts',
                path=str(p),sha256=file_hash(self.root/p),duration=len(a)/16000))
        anchor=next(r for r in rows if r['phrase']=='ehi_nira_it' and r['variant']=='spaced' and FAMILIES[r['family']]['style']=='natural')
        from scipy.io.wavfile import read
        sr,pcm=read(self.root/anchor['path']);assert sr==16000
        for i,profile in enumerate(ACOUSTIC_PROFILES):
            a=acoustic(pcm.astype('float32')/32768,profile,self.cfg['seed']+i)
            id_='acoustic-'+profile;p=Path('preview')/(id_+'.wav');self.write_wav(self.root/p,a)
            rows.append(dict(id=id_,phrase='ehi_nira_it',family=anchor['family'],preview_kind='acoustic',profile=profile,text='Ehi Nira',
                path=str(p),sha256=file_hash(self.root/p),duration=len(a)/16000))
        save(self.root/'unavailable_preview_families.json',unavailable)
        save(self.root/'preview.json',dict(config_fingerprint=self.cfg_fingerprint,rows=rows))
        print('Anteprime nuove:',len(rows),'famiglie non troncate:',len(unavailable),'(scartate per durata >1.8s)',flush=True)

    def approved(self):
        chosen=super().approved()
        variants={FAMILIES[f]['variant'] for f in chosen['ehi_nira_it']}
        if not variants.intersection({'joined_ehi','joined_ei'}):raise ValueError('Serve almeno una pronuncia legata approvata: Ehinira o Einira.')
        if not variants.intersection({'spaced','ei_spaced'}):raise ValueError('Serve almeno una pronuncia naturale separata approvata.')
        self.profiles=self.approved_profiles()
        return chosen

    def approved_profiles(self):
        payload=self.payload();approval=load(self.root/'approval.json');check_approval(payload,approval)
        result=[r['profile'] for r in payload['rows'] if r.get('preview_kind')=='acoustic' and approval['ratings'].get(r['id']) is True]
        if 'clean' not in result:raise ValueError('Il riferimento acustico pulito deve essere approvato.')
        return result

    def generate(self):
        import numpy as np
        chosen=self.approved();profiles=self.profiles
        approval_hash=digest(load(self.root/'approval.json'))
        old=self.root/'dataset.json'
        if old.exists():
            if load(old).get('approval_fingerprint')!=approval_hash:
                raise ValueError('Approvazione cambiata dopo il dataset: usa un nuovo RUN_ID per non riusare pesi precedenti.')
            print('Dataset V5 già completo');return
        # Gate checked before any deletion or mass synthesis.
        seconds=sum(self.cfg['positives'].values())*1.8+sum(self.cfg[k] for k in ('train_hard','train_speech'))*3+self.cfg['train_continuous']*8
        self.guard(seconds*32000/2**30*1.5+5,'stima V5 WAV + dipendenze')
        shutil.rmtree(self.root/'audio',ignore_errors=True);rows=[];hashes={r['sha256']:'preview' for r in self.payload()['rows']}
        def add(kind,split,phrase,family,text,a,variant=None):
            id_=len(rows)
            if id_%100==0:self.guard(.25,'generazione V5');print('WAV V5',id_,flush=True)
            profile=profiles[id_%len(profiles)] if split=='training' else 'clean'
            a=acoustic(a,profile,self.cfg['seed']+id_*7919)
            p=Path('audio')/kind/phrase/split/f'{id_:07d}.wav';self.write_wav(self.root/p,a)
            h=file_hash(self.root/p)
            if h in hashes:raise RuntimeError('Waveform identica alla preview o già generata; run fermato.')
            hashes[h]=split
            rows.append(dict(id=id_,kind=kind,split=split,phrase=phrase,family=family,text=text,variant=variant or 'negative',
                acoustic_profile=profile,path=str(p),sha256=h,duration=len(a)/16000))
        for phrase in PHRASES:
            families=chosen[phrase]
            for split,n in [('training',self.cfg['positives'][phrase]),('validation',self.cfg['val_positive']),('testing',self.cfg['test_positive'])]:
                # New stochastic WAVs; round-robin preserves approved text/style coverage in every split.
                for i in range(n):
                    family=families[i%len(families)];f=FAMILIES[family]
                    for duration_attempt in range(16):
                        a=self.synth(f['text'],family)
                        if len(a)<=28800:break
                    else:raise RuntimeError('16 sintesi oltre 1.8s: '+family)
                    if len(a)>28800:raise RuntimeError('Sintesi positiva >1.8s: non troncare; rivedere famiglia '+family)
                    add('positive',split,phrase,family,f['text'],a,f['variant'])
        all_families=sorted(set(sum(chosen.values(),[])))
        for kind in ('hard','speech'):
            for split,key in [('training','train'),('validation','val'),('testing','test')]:
                for i in range(self.cfg[f'{key}_{kind}']):
                    text=HARD[i%len(HARD)] if kind=='hard' else self.rng.choice(TEMPLATES[split]).format(obj=self.rng.choice(OBJECTS))
                    assert 'nira' not in text.casefold()
                    family=self.rng.choice(all_families);add(kind,split,'negative',family,text,self.synth(text,family))
        for i in range(self.cfg['train_continuous']):
            a=self.noise(8.,self.cfg['seed']+300000+i)*.08;cursor=self.rng.uniform(0,.4);texts=[]
            while cursor<6.5:
                text=(self.rng.choice(HARD) if self.rng.random()<.35 else self.rng.choice(TEMPLATES['training']).format(obj=self.rng.choice(OBJECTS)));family=self.rng.choice(all_families)
                u=self.synth(text,family)*self.rng.uniform(.15,.7);start=int(cursor*16000);n=min(len(u),len(a)-start)
                a[start:start+n]+=u[:n];cursor+=n/16000+self.rng.uniform(.1,1.2);texts.append(text)
            add('continuous','training','negative','mixed',' | '.join(texts),a)
        for i in range(self.cfg['train_noise']):add('noise','training','negative','procedural','',self.noise(3.2,self.cfg['seed']+i))
        for split in ('validation','testing'):
            total=60*self.cfg[f'ambient_{split}_minutes']
            for stream in range(math.ceil(total/60)):
                seconds=min(60,total-stream*60);seed=self.cfg['seed']+(100000 if split=='validation' else 200000)+stream
                rng=random.Random(seed);a=self.noise(seconds,seed)*.08;cursor=.5
                while cursor<seconds-6:
                    text=rng.choice(HARD) if rng.random()<.35 else rng.choice(TEMPLATES[split]).format(obj=rng.choice(OBJECTS))
                    assert 'nira' not in text.casefold()
                    family=rng.choice(all_families);u=self.synth(text,family)*rng.uniform(.15,.7);start=int(cursor*16000);n=min(len(u),len(a)-start)
                    a[start:start+n]+=u[:n];cursor+=n/16000+rng.uniform(.3,1.8)
                add('ambient',split,'negative','mixed','TTS italiano + rumore procedurale',a)
        save(old,dict(approval_fingerprint=approval_hash,rows=rows))
        print('Dataset V5:',len(rows),'WAV; nessuna registrazione reale.',flush=True)
        self.backup(light=True)

    def score(self,split):
        global ACTIVE_EVALUATION_PROFILES
        ACTIVE_EVALUATION_PROFILES=tuple(self.approved_profiles())
        return super().score(split)

    def report(self):
        from contextlib import redirect_stdout
        from io import StringIO
        with redirect_stdout(StringIO()):super().report()
        report=load(self.root/'evaluation.json');ops=load(self.root/'operating_points.json')
        for phrase in PHRASES:
            rows=load(self.root/'scores'/f'{phrase}_testing.json')['rows'];o=ops[phrase]
            positives=[r for r in rows if r['kind']=='positive' and r['phrase']==phrase]
            report[phrase]['recall_by_variant']={v:recall([r for r in rows if r.get('variant')==v],phrase,o['cutoff'],o['window']) for v in sorted({r['variant'] for r in positives})}
            report[phrase]['recall_by_voice']={v:recall([r for r in rows if r.get('family') in FAMILIES and FAMILIES[r['family']]['voice']==v],phrase,o['cutoff'],o['window']) for v in sorted({FAMILIES[r['family']]['voice'] for r in positives})}
        report['test_passed_descriptively']=report['test_passed_descriptively'] and all(v>=.75 for p in PHRASES for v in report[p]['recall_by_variant'].values())
        report['limitations'][0]='Cinque voci TTS italiane da due motori; nessun test su parlanti umani indipendenti.'
        report['limitations'].append('Fuori asse/distanza sono filtri digitali approssimati: non angoli o metri calibrati, nessuna misura RIR della stanza.')
        save(self.root/'evaluation.json',report);print('REPORT V5 FINALE',json.dumps(report,indent=2,ensure_ascii=False),flush=True);self.backup(light=True)


# V6: continuous synthetic room background, five Italian voices, automatic acceptance.
KOKORO_REV='f3ff3571791e39611d31c381e3a41a3af07b4987'
PIPER_VOICES=dict(VOICES)
VOICES=dict(VOICES,kokoro_sara='if_sara',kokoro_nicola='im_nicola')
TEXT_VARIANTS={
 'ehi_nira_it':{'spaced':'Ehi Nira','ei_spaced':'Ei Nira','hei_spaced':'Hei Nira','hey_spaced':'Hey Nira',
 'joined_ehi':'Ehinira','joined_ei':'Einira','joined_hei':'Heinira','joined_hey':'Heynira','pause':'Ehi, Nira'},
 'nira_it':{'solo':'Nira','calling':'Nira!','question':'Nira?'}}
FAMILIES={f'{v}-{style}-{phrase}-{variant}':dict(voice=v,length_scale=length,noise_scale=.667,noise_w_scale=.8,
 phrase=phrase,variant=variant,text=text,style=style)
 for v in VOICES for style,length in [('natural',1.),('fast',.82),('slow',1.16)]
 for phrase,variants in TEXT_VARIANTS.items() for variant,text in variants.items()}
DEFAULT=dict(DEFAULT,run_id='nyra-it-v6-004-continuous',seed=310601,
 positives={'ehi_nira_it':24000,'nira_it':16000},val_positive=900,test_positive=1200,
 context_policy='continuous-v1',auto_accept=True)
FLOORS=(-75,-60,-45)
EVAL_CONDITIONS=tuple(f'{p}__floor{db}' for p in ACOUSTIC_PROFILES for db in FLOORS)

def continuous_context(audio,seed,pre_s=4.,tail_s=1.,floor_dbfs=None):
    import numpy as np
    a=np.asarray(audio)
    if np.issubdtype(a.dtype,np.integer):a=a.astype(np.float32)/32768
    else:a=a.astype(np.float32)
    rng=np.random.default_rng(seed)
    if floor_dbfs is None:floor_dbfs=float(rng.uniform(-75,-42))
    lead=int(pre_s*16000);tail=int(tail_s*16000)
    # No digital-zero pre-roll: same background policy for all labels/splits.
    n=rng.normal(0,1,lead+len(a)+tail).astype(np.float32)
    # Half the streams have colored synthetic background; white is retained for regression.
    if seed%2==0:
        from scipy.signal import lfilter
        n=lfilter([.2],[1,-.8],n).astype(np.float32)
    n*=10**(floor_dbfs/20)/max(float(np.sqrt(np.mean(n*n))),1e-12)
    n[lead:lead+len(a)]+=a
    return np.clip(n,-1,1).astype(np.float32)

def evaluation_variants(audio,kind,seed):
    import numpy as np
    a=np.asarray(audio)
    if np.issubdtype(a.dtype,np.integer):a=a.astype(np.float32)/32768
    if kind!='positive':return [('original',continuous_context(a,seed))]
    return [(f'{p}__floor{db}',continuous_context(acoustic(a,p,seed+i*1301),seed+i*7919+j,
            floor_dbfs=db)) for i,p in enumerate(ACOUSTIC_PROFILES) for j,db in enumerate(FLOORS)]

_V5Run=Run
class Run(_V5Run):
    def ensure_voices(self):
        from huggingface_hub import hf_hub_download
        self.guard(3,'cinque voci TTS')
        folder=self.root/'voices';folder.mkdir(exist_ok=True)
        for name,remote in PIPER_VOICES.items():
            for suffix in ('','.json'):
                p=hf_hub_download('rhasspy/piper-voices',remote+suffix,revision=VOICE_REV)
                shutil.copy2(p,folder/(Path(remote).name+suffix))
            p=hf_hub_download('rhasspy/piper-voices',str(Path(remote).parent/'MODEL_CARD'),revision=VOICE_REV)
            shutil.copy2(p,folder/f'{name}_MODEL_CARD.txt')
        for filename in ['config.json','kokoro-v1_0.pth','voices/if_sara.pt','voices/im_nicola.pt','README.md','VOICES.md']:
            p=hf_hub_download('hexgrad/Kokoro-82M',filename,revision=KOKORO_REV)
            dest=folder/('kokoro_'+Path(filename).name);shutil.copy2(p,dest)
        shutil.copy2(folder/'kokoro_README.md',folder/'kokoro_MODEL_CARD.txt')

    def synth(self,text,family):
        import numpy as np
        f=FAMILIES[family]
        if not f['voice'].startswith('kokoro_'):return super().synth(text,family)
        import torch
        from kokoro import KModel,KPipeline
        from scipy.signal import resample_poly
        if not hasattr(self,'kokoro'):
            torch.set_num_threads(2)
            model=KModel(repo_id='hexgrad/Kokoro-82M',config=str(self.root/'voices/kokoro_config.json'),
                         model=str(self.root/'voices/kokoro_kokoro-v1_0.pth')).to('cpu').eval()
            self.kokoro=KPipeline(lang_code='i',repo_id='hexgrad/Kokoro-82M',model=model)
        voice=torch.load(self.root/'voices'/f'kokoro_{VOICES[f["voice"]]}.pt',map_location='cpu',weights_only=True)
        speed=self.rng.uniform(.97,1.03)/f['length_scale']
        chunks=[x.audio.detach().cpu().numpy() for x in self.kokoro(text,voice=voice,speed=speed)]
        if not chunks:raise RuntimeError('Kokoro non ha prodotto audio')
        a=resample_poly(np.concatenate(chunks),2,3).astype(np.float32)
        active=np.flatnonzero(abs(a)>.005)
        if not len(active) or not np.isfinite(a).all():raise RuntimeError('TTS non valido')
        a=a[max(0,active[0]-800):min(len(a),active[-1]+801)]
        a*=self.rng.uniform(.85,1.)
        return np.clip(a,-1,1)

    def preview(self):
        super().preview()
        payload=self.payload();ratings={r['id']:True for r in payload['rows']}
        selected=select_families(payload['rows'],ratings)
        required=set(TEXT_VARIANTS['ehi_nira_it'])
        available={FAMILIES[f]['variant'] for f in selected['ehi_nira_it']}
        if required-available:raise RuntimeError('Varianti mancanti: '+str(required-available))
        available_voices={FAMILIES[f]['voice'] for p in selected.values() for f in p}
        if available_voices!=set(VOICES):raise RuntimeError('Non tutte le cinque voci hanno sample validi')
        save(self.root/'approval.json',dict(confirmed=True,fingerprint=digest(payload),ratings=ratings,selected=selected,
            authorization='User: approva di default già tutti i sample non chiedere verifiche',
            policy='automatic_acceptance_explicit_user_instruction',timestamp=time.time()))
        self.approved();print('AUTO-ACCETTATI',len(ratings),'sample tecnicamente validi',flush=True)

_V5_choose=choose_operating_point
def choose_operating_point(rows,phrase,target_faph=.5,min_recall=.85):
    op=_V5_choose(rows,phrase,target_faph,min_recall)
    conditions=sorted({r['condition'] for r in rows if r['kind']=='positive' and r['phrase']==phrase})
    for item in op['grid']:
        item['recall_by_condition']={c:recall([r for r in rows if r['condition']==c],phrase,item['cutoff'],item['window']) for c in conditions}
        item['feasible']=item['feasible'] and min(item['recall_by_condition'].values())>=.75
    good=[r for r in op['grid'] if r['feasible']]
    best=max(good,key=lambda x:(x['recall'],-x['hard_fpr'],-x['faph'],x['cutoff'],-x['window'])) if good else min(op['grid'],key=lambda x:(x['faph'],-x['recall']))
    return dict(best,grid=op['grid'])

_V6ReportRun=Run
class Run(_V6ReportRun):
    def report(self):
        from contextlib import redirect_stdout
        from io import StringIO
        with redirect_stdout(StringIO()):super().report()
        report=load(self.root/'evaluation.json')
        report['test_passed_descriptively']=report['test_passed_descriptively'] and all(
            item[phrase]>=.75 for phrase in PHRASES for item in report[phrase]['recall_by_condition'].values())
        report['limitations'].append('Il fondo continuo e i cinque preset TTS non sostituiscono test su voce umana e stanza reali.')
        save(self.root/'evaluation.json',report)
        print('REPORT V6 FINALE',json.dumps(report,indent=2,ensure_ascii=False),flush=True)
        self.backup(light=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['preview','generate','features','train','score','calibrate','report','export','backup'])
    parser.add_argument('--resume',action='store_true');parser.add_argument('--root',required=True);parser.add_argument('--phrase',choices=list(PHRASES));parser.add_argument('--split',choices=['validation','testing'])
    args=parser.parse_args();run=Run(args.root)
    if args.action=='train':run.train(args.phrase,args.resume)
    elif args.action=='score':run.score(args.split)
    else:getattr(run,args.action)()
