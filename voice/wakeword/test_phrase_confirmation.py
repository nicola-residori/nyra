import json
import unittest
from pathlib import Path

import numpy as np

from phrase_confirmation import PhraseConfirmation


class Tests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).parent / 'profiles/ctc-it/vocab.json'
        self.vocab = json.loads(path.read_text())
        self.gate = PhraseConfirmation(self.vocab)

    def frames(self, text, trailing=5):
        tokens = ['<pad>'] * 15
        for c in text:
            tokens.extend([c, c, '<pad>'])
        tokens.extend(['<pad>'] * trailing)
        logits = np.full((1, len(tokens), len(self.vocab)), -15.0)
        for i, token in enumerate(tokens):
            logits[0, i, self.vocab[token]] = 5
        return logits

    def test_accepts_greeting_name_with_optional_gap_and_accents(self):
        for text in ['einira', 'ei|nira', 'è|nira', 'ai|nirà']:
            self.assertEqual(self.gate.cost(self.frames(text)), 0)

    def test_confusable_names_and_solo_name_pay_penalty(self):
        for text in ['nira', 'ei|mira', 'ei|nera', 'ei|nina', 'ei|rani', '']:
            self.assertGreaterEqual(self.gate.cost(self.frames(text)), 20)

    def test_stale_phrase_is_excluded(self):
        self.assertGreaterEqual(self.gate.cost(self.frames('ei|nira', trailing=80)), 20)

class StreamingDecisionTests(unittest.TestCase):
    def decision(self, prior_frames, cost, probability=.99, selective=False):
        from unittest.mock import Mock
        from test_candidate_history import engine
        candidate = engine(None)
        candidate.config.update(verifier_cutoff=.98, phrase_max_cost=14.,
                                max_prior_speech_frames=6)
        if selective:
            candidate.config.update(clear_phrase_cutoff=.85, clear_phrase_max_cost=2.)
        candidate.vad = Mock()
        candidate.vad.probabilities.return_value = [1.] * prior_frames + [0.] * (48 - prior_frames) + [1.] * 40
        candidate.session = Mock()
        candidate.session.run.return_value = [np.array([probability]), None]
        candidate.phrase_gate = Mock()
        candidate.phrase_gate.cost.return_value = cost
        for _ in range(9):
            candidate.feed(bytes(2560))
        return bool(candidate.detections)

    def test_rejects_continuous_speech_even_with_perfect_letter_match(self):
        self.assertFalse(self.decision(7, 0))
        self.assertTrue(self.decision(6, 0))

    def test_requires_both_acoustic_and_letter_confirmation(self):
        self.assertFalse(self.decision(0, 15))
        self.assertFalse(self.decision(0, 0, probability=.97))
        self.assertTrue(self.decision(0, 14))

    def test_recovers_only_clear_marginal_calls_after_a_quiet_lead_in(self):
        self.assertTrue(self.decision(6, 2, probability=.90, selective=True))
        self.assertFalse(self.decision(7, 2, probability=.90, selective=True))
        self.assertFalse(self.decision(0, 2.1, probability=.97, selective=True))
        self.assertFalse(self.decision(0, 0, probability=.84, selective=True))
        self.assertTrue(self.decision(6, 14, probability=.99, selective=True))
