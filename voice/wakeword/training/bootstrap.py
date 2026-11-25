"""Isolated Colab environment. Never modifies the V6 environment or production server."""
import sys,subprocess,os
from pathlib import Path

def run(*a):subprocess.run(list(a),check=True)
run(sys.executable,'-m','pip','install','-q','uv==0.9.7')
uv=[sys.executable,'-m','uv'];env=Path('/content/nyra_oww_env312');py=str(env/'bin/python')
if not env.exists():run(*uv,'venv','--python','3.12',str(env))
run(*uv,'pip','install','--python',py,'numpy==2.1.3','scipy==1.15.3','tensorflow[and-cuda]==2.19.1','keras==3.10.0','onnxruntime-gpu==1.23.2','scikit-learn==1.6.1','tqdm==4.67.1','requests==2.32.3')
for directory,url,commit in [('/content/nyra_oww_source','https://github.com/dscripka/openWakeWord.git','368c03716d1e92591906a84949bc477f3a834455'),('/content/nyra_pyoww_source','https://github.com/rhasspy/pyopen-wakeword.git','6bc5c5f5c9c71e46a723b6c9277b1d50f2ba13fd')]:
 if not Path(directory).exists():run('git','clone','--quiet',url,directory)
 run('git','-C',directory,'checkout','--quiet',commit)
run(*uv,'pip','install','--python',py,'--no-deps','-e','/content/nyra_oww_source')
run(py,'-c',"from openwakeword.utils import download_models; download_models(model_names=['__frontend_only__'])")
run(py,'-c',"import onnxruntime as ort; ort.preload_dlls(); import numpy as np; from openwakeword.utils import AudioFeatures; f=AudioFeatures(device='gpu',ncpu=2); assert f.onnx_execution_provider=='CUDAExecutionProvider',f.onnx_execution_provider; x=f.embed_clips(np.zeros((2,51200),dtype=np.int16),batch_size=2); print('FRONTEND_GPU_OK',x.shape); assert x.shape[0]==2 and x.shape[2]==96")
print('ENVIRONMENT_READY',py,flush=True)
