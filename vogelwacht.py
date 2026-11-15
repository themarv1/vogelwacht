#!/usr/bin/env python3
"""Vogelwacht – KI-Vogelerkennung im Vogelhaus mit dem Coralboard SL.

Ablauf: Kamera -> Bewegungserkennung -> Vogelerkennung (YOLOv8n auf der
Torq-NPU) -> Artbestimmung (iNaturalist-Vogelmodell, CPU) -> Besuch
zusammenfassen -> SQLite + Foto -> Webseite / optional Webhook.

Aufruf:
    python3 vogelwacht.py                  # Dauerbetrieb
    python3 vogelwacht.py --test-image x.jpg   # ein Foto pruefen
    python3 vogelwacht.py --config andere.toml
"""

import argparse
import json
import os
import signal
import sys
import threading
import time
import tomllib
import urllib.request
from datetime import datetime

import cv2
import numpy as np

from classifier import SpeciesClassifier
from species_de import GERMAN_NAMES
from visits import UNKNOWN, VisitTracker

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def log(*args):
    print(datetime.now().strftime('%H:%M:%S'), *args, flush=True)


def load_config(path):
    with open(path, 'rb') as f:
        cfg = tomllib.load(f)

    def resolve(section, key):
        p = cfg[section][key]
        if p and not os.path.isabs(p):
            cfg[section][key] = os.path.join(BASE_DIR, p)

    for section, key in (('classifier', 'model'), ('classifier', 'labels'), ('storage', 'data_dir')):
        resolve(section, key)
    return cfg


def crop_box(frame, box, margin):
    """Ausschnitt um eine Box (x, y, w, h) mit Rand, quadratisch, im Bild begrenzt."""
    h_img, w_img = frame.shape[:2]
    x, y, w, h = box
    side = int(max(w, h) * (1 + 2 * margin))
    cx, cy = x + w // 2, y + h // 2
    x0, y0 = max(0, cx - side // 2), max(0, cy - side // 2)
    x1, y1 = min(w_img, x0 + side), min(h_img, y0 + side)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    return frame[y0:y1, x0:x1]


def rotate(frame, degrees):
    codes = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
    return cv2.rotate(frame, codes[degrees]) if degrees in codes else frame


def jpeg(frame, quality=85):
    ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else None


class MotionDetector:
    """Einfacher Bildvergleich auf einem verkleinerten Graubild."""

    def __init__(self, threshold, min_area):
        self.threshold = threshold
        self.min_area = min_area
        self._prev = None

    def update(self, frame):
        small = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(frame, (160, 120)), cv2.COLOR_BGR2GRAY), (5, 5), 0)
        prev, self._prev = self._prev, small
        if prev is None:
            return False
        changed = np.count_nonzero(cv2.absdiff(small, prev) > self.threshold)
        return changed / small.size >= self.min_area


class Camera:
    """Kamera mit Hintergrund-Thread, der immer nur das neueste Bild behaelt.

    Nutzt die Kamera-Klasse aus den Synaptics-Beispielen (app_utils.camera):
    Sie findet den Sensor der CSI-Kamera und stellt Belichtung/Verstaerkung
    ein. Weil sich das Licht draussen aendert, wird das regelmaessig wiederholt.
    Ohne app_utils wird die Kamera direkt per OpenCV/V4L2 geoeffnet.
    """

    def __init__(self, cfg):
        dev = cfg['device']
        self._retune_s = cfg.get('retune_exposure_min', 10) * 60
        self._last_tune = time.time()
        self._cam = None
        try:
            from app_utils.camera import Camera as SynapticsCamera
            self._cam = SynapticsCamera(
                device=dev, width=cfg['width'], height=cfg['height'], fps=cfg['fps'],
                controls=cfg.get('controls') or None, control_device=cfg.get('control_device') or None,
            ).open()
            self.cap = self._cam
        except ImportError:
            if cfg.get('control_device') and cfg.get('controls'):
                self._set_controls(cfg['control_device'], cfg['controls'])
            index = int(dev.replace('/dev/video', '')) if dev.startswith('/dev/video') else dev
            self.cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
            if not self.cap.isOpened():
                raise RuntimeError('Kamera {} laesst sich nicht oeffnen'.format(dev))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg['width'])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg['height'])
            self.cap.set(cv2.CAP_PROP_FPS, cfg['fps'])
        self._lock = threading.Lock()
        self._frame = None
        self._seq = 0
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name='camera')
        self._thread.start()

    @staticmethod
    def _set_controls(device, controls):
        import subprocess
        args = ','.join('{}={}'.format(k, v) for k, v in controls.items())
        subprocess.run(['v4l2-ctl', '-d', device, '--set-ctrl', args], check=False)

    def _retune(self):
        """Belichtung nachstellen (nur CSI-Kamera ueber app_utils)."""
        if self._cam is None or not getattr(self._cam, 'sensor_subdev', None):
            return
        try:
            self._cam.tune_csi_exposure()
        except Exception as e:  # Belichtung ist nicht kritisch, weiterlaufen
            log('Belichtung nachstellen fehlgeschlagen:', e)

    def _loop(self):
        while self._running:
            if self._retune_s and time.time() - self._last_tune > self._retune_s:
                self._retune()
                self._last_tune = time.time()
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            with self._lock:
                self._frame = frame
                self._seq += 1

    def read(self):
        """(Folgenummer, Bild) des neuesten Bildes oder (0, None)."""
        with self._lock:
            return self._seq, (None if self._frame is None else self._frame.copy())

    def close(self):
        self._running = False
        self._thread.join(timeout=1)
        if self._cam is not None:
            self._cam.close()
        else:
            self.cap.release()


def notify(cfg, visit, name, image_rel):
    url = cfg.get('webhook_url')
    if not url:
        return
    only = cfg.get('only_species') or []
    if only and visit.species not in only:
        return
    body = json.dumps({
        'art': name, 'lateinisch': visit.species, 'sicherheit': round(visit.confidence, 3),
        'beginn': datetime.fromtimestamp(visit.start).isoformat(timespec='seconds'),
        'dauer_s': round(visit.end - visit.start), 'bild': image_rel,
    }).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req, timeout=5).close()
    except OSError as e:
        log('Webhook fehlgeschlagen:', e)


def make_classifier(cfg):
    c = cfg['classifier']
    allowed = list(GERMAN_NAMES) if c.get('restrict_to_garden_birds', True) else None
    return SpeciesClassifier(c['model'], c['labels'], allowed=allowed, threads=c.get('threads', 2))


def make_detector(cfg):
    from detector import BirdDetector
    d = cfg['detector']
    return BirdDetector(d['examples_dir'], d['model'], d['labels'], conf=d.get('min_score', 0.35))


def test_image(cfg, path):
    """Prueft ein einzelnes Foto: Vogel erkennen und Art bestimmen."""
    frame = cv2.imread(path)
    if frame is None:
        sys.exit('Bild nicht lesbar: ' + path)
    clf = make_classifier(cfg)
    det = make_detector(cfg)
    try:
        birds = det.detect(frame)
        log('Voegel gefunden:', len(birds), '({} ms NPU)'.format(det.infer_ms))
        margin = cfg['classifier'].get('crop_margin', 0.2)
        for score, box in birds:
            crop = crop_box(frame, box, margin)
            if crop is None:
                continue
            t0 = time.perf_counter()
            top = clf.classify(crop)
            ms = (time.perf_counter() - t0) * 1000
            log('Vogel {:.0%} bei {}: '.format(score, box) + ', '.join(
                '{} {:.0%}'.format(clf.display_name(n, GERMAN_NAMES), p) for n, p in top[:3]),
                '({:.0f} ms CPU)'.format(ms))
            x, y, w, h = box
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 200, 0), 2)
            if top:
                cv2.putText(frame, clf.display_name(top[0][0], GERMAN_NAMES), (x, max(15, y - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 0), 2)
        out = os.path.splitext(path)[0] + '_ergebnis.jpg'
        cv2.imwrite(out, frame)
        log('Ergebnis gespeichert:', out)
    finally:
        det.close()


def run(cfg):
    from storage import Storage
    from web import SharedState, start_web

    storage = Storage(cfg['storage']['data_dir'])
    state = SharedState()
    if cfg['web'].get('enabled', True):
        start_web(storage, state, cfg['web']['host'], cfg['web']['port'])
        log('Webseite auf Port', cfg['web']['port'])

    clf = make_classifier(cfg)
    det = make_detector(cfg)
    cam = Camera(cfg['camera'])
    v = cfg['visits']
    tracker = VisitTracker(gap_s=v['gap_s'], min_frames=v['min_frames'], min_confidence=v['min_confidence'])
    mcfg = cfg['motion']
    motion = MotionDetector(mcfg['threshold'], mcfg['min_area']) if mcfg.get('enabled', True) else None
    sched = cfg['schedule']
    rot = cfg['camera'].get('rotate', 0)
    margin = cfg['classifier'].get('crop_margin', 0.2)
    clf_interval = cfg['classifier'].get('interval_s', 0.5)
    live_interval = cfg['web'].get('live_interval_s', 2)

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    last_seq = 0
    last_motion = 0.0
    last_clf = 0.0
    last_live = 0.0
    last_cleanup = 0.0

    def finish(visit):
        name = UNKNOWN if visit.species == UNKNOWN else clf.display_name(visit.species, GERMAN_NAMES)
        data = jpeg(visit.best_image) if visit.best_image is not None else None
        rel = storage.add_visit(visit, name, data)
        log('Besuch: {} ({:.0%}, {} Bilder, {:.0f} s)'.format(
            name, visit.confidence, visit.frames, visit.end - visit.start))
        notify(cfg['notify'], visit, name, rel)

    log('Vogelwacht laeuft.')
    try:
        while not stop.is_set():
            now = time.time()
            if now - last_cleanup > 3600:
                storage.cleanup_images(cfg['storage'].get('keep_images_days', 30))
                last_cleanup = now

            hour = datetime.now().hour
            if not (sched['active_from'] <= hour < sched['active_until']):
                state.status = 'Nachtpause'
                visit = tracker.flush()
                if visit:
                    finish(visit)
                stop.wait(30)
                continue

            seq, frame = cam.read()
            if frame is None or seq == last_seq:
                stop.wait(0.01)
                continue
            last_seq = seq
            frame = rotate(frame, rot)

            if now - last_live >= live_interval:
                state.set_live(jpeg(frame, 70))
                last_live = now

            if motion is not None and motion.update(frame):
                last_motion = now
            watching = motion is None or tracker.active or now - last_motion < mcfg['active_s']
            if not watching:
                state.status = 'wartet auf Bewegung'
                visit = tracker.tick(now)
                if visit:
                    finish(visit)
                stop.wait(1 / mcfg['idle_fps'])
                continue

            state.status = 'beobachtet'
            birds = det.detect(frame)
            if birds and now - last_clf >= clf_interval:
                score, box = max(birds, key=lambda b: b[0])
                crop = crop_box(frame, box, margin)
                if crop is not None:
                    top = clf.classify(crop)
                    last_clf = now
                    if top:
                        tracker.observe(now, top, score, frame)
                        state.status = 'Vogel: ' + clf.display_name(top[0][0], GERMAN_NAMES)
                    else:  # keine erlaubte Art passt, Besuch trotzdem offen halten
                        tracker.keep_alive(now)
            elif birds:
                tracker.keep_alive(now)

            visit = tracker.tick(now)
            if visit:
                finish(visit)
    finally:
        visit = tracker.flush()
        if visit:
            finish(visit)
        cam.close()
        det.close()
        log('Vogelwacht beendet.')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--config', default=os.path.join(BASE_DIR, 'config.toml'))
    ap.add_argument('--test-image', help='ein Foto pruefen statt Dauerbetrieb')
    args = ap.parse_args()
    cfg = load_config(args.config)
    if args.test_image:
        test_image(cfg, args.test_image)
    else:
        run(cfg)


if __name__ == '__main__':
    main()
