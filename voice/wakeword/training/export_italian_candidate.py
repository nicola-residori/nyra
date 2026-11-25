"""Export research candidate only. Does not authorize installation."""
from pathlib import Path
import os,json,hashlib,time,gc,shutil,importlib.util
os.environ.update(USE_TF='0',USE_FLAX='0')
import torch,numpy as np,onnxruntime as ort
from transformers import Wav2Vec2ForCTC
from onnxruntime.quantization import quantize_dynamic,QuantType
s=importlib.util.spec_from_file_location('v','/content/italian_verifier_v2.py');v=importlib.util.module_from_spec(s);s.loader.exec_module(v)
OUT=Path('/content/nyra_italian_candidate_v1');OUT.mkdir(exist_ok=True);BKP=v.BKP.parent/'italian_candidate_v1';BKP.mkdir(exist_ok=True)
torch.set_num_threads(2)
class Candidate(torch.nn.Module):
 def __init__(self):
  super().__init__();self.encoder=Wav2Vec2ForCTC.from_pretrained(v.ID,revision=v.REV,attn_implementation='eager').wav2vec2.eval();self.head=v.Head().eval();self.head.load_state_dict(torch.load(v.ROOT/'best.pt',map_location='cpu',weights_only=True));length=int(self.encoder._get_feat_extract_output_lengths(torch.tensor(v.N)));weights=torch.zeros(32,length)
  for i in range(32):
   start=i*length//32;end=((i+1)*length+31)//32;weights[i,start:end]=1/(end-start)
  self.register_buffer('pool',weights)
 def forward(self,audio):
  x=(audio-audio.mean(-1,keepdim=True))/torch.sqrt(audio.var(-1,keepdim=True,unbiased=False)+1e-7);h=self.encoder(x).last_hidden_state;features=torch.matmul(self.pool,h).half().float();return self.head(features).sigmoid()
model=Candidate().eval();plan=v.plan_training();waves=[v.training_audio(next(r for r in plan if r['label']==label)) for label in [1,0]]+[np.random.default_rng(81).normal(0,.0001,v.N).astype(np.float32)];expected=[]
with torch.inference_mode():
 for a in waves:expected.append(float(model(torch.from_numpy(a[None]))[0]))
print('EXPORT_TORCH_REFERENCE',expected,flush=True)
fp=OUT/'verifier.fp32.onnx';q=OUT/'verifier.int8.onnx'
if not fp.exists():torch.onnx.export(model,torch.from_numpy(waves[0][None]),str(fp),input_names=['audio'],output_names=['probability'],opset_version=17,dynamo=False,do_constant_folding=True)
np.savez(OUT/'parity_inputs.npz',audio=np.stack(waves),expected=np.array(expected));del model;gc.collect()
opts=ort.SessionOptions();opts.intra_op_num_threads=2;opts.inter_op_num_threads=1
sess=ort.InferenceSession(str(fp),opts,providers=['CPUExecutionProvider']);actual=[float(sess.run(None,{'audio':a[None]})[0][0]) for a in waves];assert np.allclose(actual,expected,atol=.002),(actual,expected);del sess;gc.collect();print('EXPORT_FP32_PARITY',actual,flush=True)
if not q.exists():quantize_dynamic(str(fp),str(q),weight_type=QuantType.QInt8,per_channel=True,op_types_to_quantize=['MatMul','Gemm'])
sess=ort.InferenceSession(str(q),opts,providers=['CPUExecutionProvider']);quant=[float(sess.run(None,{'audio':a[None]})[0][0]) for a in waves];print('EXPORT_INT8_PARITY',quant,'absolute_error',[abs(a-b) for a,b in zip(quant,expected)],flush=True)
lat=[]
for i in range(5):
 start=time.monotonic();sess.run(None,{'audio':waves[i%len(waves)][None]});lat.append(time.monotonic()-start)
config=dict(status='research candidate, NOT approved for installation',phrase='Ehi Nira',solo_nira_enabled=False,all_audio_synthetic=True,primary_cutoff=.4,primary_consecutive_frames=2,verifier_cutoff=.2,verifier_window_samples=v.N,verifier_post_trigger_seconds=.24,vad_cutoff=.1,vad_min_speech_seconds=.096,refractory_seconds=2.,foundation=v.ID,foundation_revision=v.REV,head='italian_verifier_v2',head_sha256=hashlib.sha256((v.ROOT/'best.pt').read_bytes()).hexdigest(),validation_hits=930,validation_total=945,validation_ambient_events=2,validation_ambient_minutes=65,heldout_test=False,human_test=False,colab_cpu_p50_seconds=float(np.median(lat)),int8_requires_full_revalidation=True)
(OUT/'config.json').write_text(json.dumps(config,indent=2));shutil.copy2('/content/nyra_italian_vad/silero_vad.onnx',OUT/'silero_vad.onnx')
for name in ['verifier.int8.onnx','config.json','silero_vad.onnx','parity_inputs.npz']:
 src=OUT/name;dst=BKP/name;tmp=dst.with_suffix('.partial');shutil.copy2(src,tmp);assert hashlib.sha256(src.read_bytes()).digest()==hashlib.sha256(tmp.read_bytes()).digest();tmp.replace(dst)
print('ITALIAN_CANDIDATE_EXPORTED',q.stat().st_size,'CPU_p50',float(np.median(lat)),flush=True)
