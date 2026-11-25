"""Replay saved candidate windows from the original synthetic benchmark."""
import argparse
import hashlib
import importlib.util
import json
import random
from pathlib import Path

import numpy as np
import onnxruntime as ort

from evaluate_candidate import render
from phrase_confirmation import PhraseConfirmation
from candidate_engine import VoiceGate


def replay(data, results, profile, split):
    config = json.loads((profile / 'config.json').read_text())
    gate = PhraseConfirmation(json.loads((profile / 'vocab.json').read_text()))
    vad = VoiceGate(profile / 'silero_vad.onnx')
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(profile / 'verifier.int8.onnx'), options,
                                   providers=['CPUExecutionProvider'])
    spec = importlib.util.spec_from_file_location('original_worker', data / 'original_worker.py')
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    plan = {hashlib.sha256(json.dumps(x, sort_keys=True).encode()).hexdigest(): x
            for x in json.loads((data / 'plan.json').read_text())}
    with results.open() as src:
        rows = [r for line in src if (r := json.loads(line))['split'] == split]
    def positive(r):
        return r['kind'] == 'positive' and r['phrase'] == 'ehi_nira_it'
    positives = random.Random(9031).sample([r for r in rows if positive(r)], 60)
    negatives = [r for r in rows if not positive(r)]
    summary = {}
    for row in positives + negatives:
        item = plan[row['key']]
        group = row['kind'] if positive(row) or row['kind'] != 'positive' else 'solo'
        stats = summary.setdefault(group, dict(cases=0, seconds=0., previous_events=0, events=0, hits=0))
        stats['cases'] += 1
        stats['seconds'] += row['duration']
        pcm = None
        hit = False
        for event in row['candidates']:
            previous = event.get('probability')
            if previous is None or previous < min(.98, config.get('clear_phrase_cutoff', config['verifier_cutoff'])):
                continue
            if pcm is None:
                pcm = render(item, data, worker)
            end = round(event['t'] * 16000)
            audio = pcm[max(0, end - 44800):end].astype(np.float32) / 32768
            audio = np.pad(audio, (44800 - len(audio), 0))
            probability, logits = session.run(None, {'audio': audio[None]})
            if abs(probability.item() - previous) > 1e-4:
                raise ValueError('Acoustic parity failed at ' + row['key'])
            score = probability.item()
            if score >= config['verifier_cutoff']:
                accepted = gate.cost(logits) <= config['phrase_max_cost']
            else:
                accepted = ('clear_phrase_cutoff' in config and score >= config['clear_phrase_cutoff']
                            and gate.cost(logits) <= config['clear_phrase_max_cost'])
            prior_frames = sum(p >= .5 for p in vad.probabilities(audio)[:48])
            accepted = accepted and prior_frames <= config['max_prior_speech_frames']
            stats['previous_events'] += int(previous >= .98)
            stats['events'] += int(accepted)
            if accepted and (not positive(row) or 4 <= event['t'] <= 5 + item['row']['duration']):
                hit = True
        stats['hits'] += int(hit)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('data', 'results', 'profile'):
        parser.add_argument(arg, type=Path)
    parser.add_argument('split', choices=['validation', 'testing'])
    print(json.dumps(replay(**vars(parser.parse_args())), indent=2))
