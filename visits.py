"""Fasst einzelne Erkennungen zu Vogelbesuchen zusammen.

Ein Besuch beginnt mit der ersten Erkennung eines Vogels und endet, wenn
`gap_s` Sekunden lang kein Vogel mehr gesehen wurde. Die Art wird ueber alle
Bilder des Besuchs gemittelt, damit ein einzelnes unscharfes Bild das
Ergebnis nicht verfaelscht. Reine Logik ohne Kamera/NPU, damit testbar.
"""

from dataclasses import dataclass, field

UNKNOWN = 'unbekannt'


@dataclass
class Visit:
    start: float
    end: float
    species: str            # lateinischer Name oder UNKNOWN
    confidence: float       # gemittelte Wahrscheinlichkeit der Art (0..1)
    frames: int             # Anzahl klassifizierter Bilder
    top: list               # [(art, wahrscheinlichkeit), ...] absteigend
    best_image: object = None  # bestes Bild (BGR-Array) oder None


@dataclass
class _Running:
    start: float
    last_seen: float
    frames: int = 0
    prob_sum: dict = field(default_factory=dict)
    best_score: float = -1.0
    best_image: object = None


class VisitTracker:
    def __init__(self, gap_s=30.0, min_frames=2, min_confidence=0.5):
        self.gap_s = gap_s
        self.min_frames = min_frames
        self.min_confidence = min_confidence
        self._cur = None

    @property
    def active(self):
        return self._cur is not None

    def observe(self, now, species_probs, det_score, image=None):
        """Eine Erkennung: species_probs = [(art, wahrscheinlichkeit), ...]."""
        if self._cur is None:
            self._cur = _Running(start=now, last_seen=now)
        cur = self._cur
        cur.last_seen = now
        cur.frames += 1
        for name, p in species_probs:
            cur.prob_sum[name] = cur.prob_sum.get(name, 0.0) + p
        top_p = species_probs[0][1] if species_probs else 0.0
        score = det_score * top_p
        if score > cur.best_score:
            cur.best_score = score
            cur.best_image = image

    def keep_alive(self, now):
        """Vogel ist noch da, wurde aber nicht klassifiziert: Besuch offen halten."""
        if self._cur is not None:
            self._cur.last_seen = now

    def tick(self, now):
        """Liefert einen abgeschlossenen Besuch oder None."""
        cur = self._cur
        if cur is None or now - cur.last_seen < self.gap_s:
            return None
        self._cur = None
        if cur.frames < self.min_frames:
            return None  # zu kurz, vermutlich Fehlerkennung
        return self._finish(cur)

    def flush(self):
        """Laufenden Besuch sofort abschliessen (z. B. beim Beenden)."""
        cur, self._cur = self._cur, None
        if cur is None or cur.frames < self.min_frames:
            return None
        return self._finish(cur)

    def _finish(self, cur):
        means = sorted(((n, s / cur.frames) for n, s in cur.prob_sum.items()),
                       key=lambda x: x[1], reverse=True)
        species, conf = means[0] if means else (UNKNOWN, 0.0)
        if conf < self.min_confidence:
            species = UNKNOWN
        return Visit(start=cur.start, end=cur.last_seen, species=species, confidence=conf,
                     frames=cur.frames, top=means[:3], best_image=cur.best_image)
