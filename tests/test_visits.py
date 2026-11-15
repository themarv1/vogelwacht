"""Tests fuer die Besuchslogik (laufen ohne Board: python3 tests/test_visits.py)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from visits import UNKNOWN, VisitTracker  # noqa: E402


class VisitTrackerTest(unittest.TestCase):
    def test_visit_ends_after_gap(self):
        t = VisitTracker(gap_s=30, min_frames=2, min_confidence=0.5)
        t.observe(0, [('Parus major', 0.9), ('Cyanistes caeruleus', 0.1)], 0.8, 'a')
        t.observe(1, [('Parus major', 0.7), ('Cyanistes caeruleus', 0.3)], 0.9, 'b')
        self.assertIsNone(t.tick(20))
        v = t.tick(31.5)
        self.assertIsNotNone(v)
        self.assertEqual(v.species, 'Parus major')
        self.assertAlmostEqual(v.confidence, 0.8)
        self.assertEqual(v.frames, 2)
        self.assertEqual(v.best_image, 'a')  # 0.8*0.9 > 0.9*0.7
        self.assertFalse(t.active)

    def test_short_visit_discarded(self):
        t = VisitTracker(gap_s=30, min_frames=2)
        t.observe(0, [('Parus major', 0.9)], 0.8)
        self.assertIsNone(t.tick(40))
        self.assertFalse(t.active)

    def test_low_confidence_unknown(self):
        t = VisitTracker(gap_s=5, min_frames=2, min_confidence=0.6)
        t.observe(0, [('Parus major', 0.5), ('Turdus merula', 0.5)], 0.8)
        t.observe(1, [('Turdus merula', 0.55), ('Parus major', 0.45)], 0.8)
        v = t.tick(10)
        self.assertEqual(v.species, UNKNOWN)
        self.assertEqual(v.top[0][0], 'Turdus merula')

    def test_keep_alive_extends_visit(self):
        t = VisitTracker(gap_s=10, min_frames=2)
        t.observe(0, [('Parus major', 0.9)], 0.8)
        t.observe(1, [('Parus major', 0.9)], 0.8)
        t.keep_alive(9)
        self.assertIsNone(t.tick(15))
        v = t.tick(19.5)
        self.assertEqual(v.end, 9)
        self.assertAlmostEqual(v.confidence, 0.9)  # keep_alive verwaessert nichts

    def test_flush(self):
        t = VisitTracker(gap_s=30, min_frames=1)
        self.assertIsNone(t.flush())
        t.observe(0, [('Sitta europaea', 0.95)], 0.7)
        v = t.flush()
        self.assertEqual(v.species, 'Sitta europaea')
        self.assertFalse(t.active)


if __name__ == '__main__':
    unittest.main()
