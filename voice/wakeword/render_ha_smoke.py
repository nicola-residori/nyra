"""Emit only approved synthetic PCM to the caller's RAM, never play audio."""
from pathlib import Path
import json,sys,importlib.util
import numpy as np
from scipy.io.wavfile import read
from evaluate_candidate import render
root=Path('testdata');spec=importlib.util.spec_from_file_location('original',root/'original_worker.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
plan=json.loads((root/'plan.json').read_text());item=next(x for x in plan if x['split']=='validation' and x['row']['phrase']=='ehi_nira_it' and x['condition']=='clean__floor-60');pcm=render(item,root,old)
command_row=next(x['row'] for x in plan if x['row']['kind']=='hard' and x['row']['text']=='Apri la finestra');sr,command=read(root/command_row['path']);assert sr==16000
start=round((4+item['row']['duration']+.08)*16000);output=np.zeros(160000,dtype='<i2');output[:len(pcm)]=pcm;output[start:start+len(command)]=command
sys.stdout.buffer.write(output.tobytes())
