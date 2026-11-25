"""Score an ordered Italian greeting and name without constructing a transcript."""
import unicodedata

import numpy as np


def phrase_matches(config, acoustic, primary, cost, prior_frames):
    """Apply the same decision to a live candidate and a benchmark replay."""
    if prior_frames > config['max_prior_speech_frames']:
        return False
    if acoustic >= config['verifier_cutoff']:
        return cost <= config['phrase_max_cost']
    if 'clear_phrase_cutoff' not in config or acoustic < config['clear_phrase_cutoff']:
        return False
    if (prior_frames == 0 and 'quiet_primary_cutoff' in config
            and primary >= config['quiet_primary_cutoff']):
        return cost <= config['quiet_phrase_max_cost']
    return cost <= config['clear_phrase_max_cost']


class PhraseConfirmation:
    def __init__(self, vocabulary):
        def fold(token):
            return ''.join(c for c in unicodedata.normalize('NFD', token)
                           if not unicodedata.combining(c))
        self.letters = {letter: [idx for token, idx in vocabulary.items()
                                 if fold(token) == letter]
                        for letter in 'aeinr'}
        self.gaps = [vocabulary['<pad>'], vocabulary['|']]

    def cost(self, logits):
        # 20 ms encoder frames. Search the end of the candidate window so a
        # greeting elsewhere in the buffer cannot confirm an unrelated sound.
        frames = logits[0, -65:]
        if not np.isfinite(frames).all() or not np.any(np.ptp(frames, axis=1) > 0):
            return float('inf')
        peak = frames.max(axis=1)
        letter_cost = {letter: peak - frames[:, indices].max(axis=1)
                       for letter, indices in self.letters.items()}
        gap = peak - frames[:, self.gaps].max(axis=1)
        # Columns alternate letter and blank. Every letter must consume a
        # distinct frame, and internal unrelated speech carries a penalty.
        best = float('inf')
        for phrase in ('einira', 'enira', 'ainira'):
            emissions = np.stack([cost for c in phrase
                                  for cost in (letter_cost[c], gap)], axis=1)[:, :-1]
            prev = np.full(emissions.shape[1], np.inf)
            for t, frame in enumerate(emissions):
                nxt = prev.copy()
                np.minimum(nxt[1:], prev[:-1], out=nxt[1:])
                np.minimum(nxt[2::2], prev[:-2:2], out=nxt[2::2])
                nxt[0] = 0
                prev = nxt + frame
                if t >= len(frames) - 27:
                    best = min(best, prev[-1])
        return float(best)
