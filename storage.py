"""Speichert Besuche in SQLite und das beste Foto als JPEG auf der microSD."""

import os
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timedelta

SCHEMA = """
CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start REAL NOT NULL,
    end REAL NOT NULL,
    species TEXT NOT NULL,
    name TEXT NOT NULL,
    confidence REAL NOT NULL,
    frames INTEGER NOT NULL,
    image TEXT
);
CREATE INDEX IF NOT EXISTS visits_start ON visits(start);
"""


class Storage:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.image_dir = os.path.join(data_dir, 'images')
        os.makedirs(self.image_dir, exist_ok=True)
        self._lock = threading.Lock()  # Webserver liest aus einem anderen Thread
        self._db = sqlite3.connect(os.path.join(data_dir, 'visits.db'), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)

    def add_visit(self, visit, name, jpeg_bytes=None):
        rel = None
        if jpeg_bytes is not None:
            t = datetime.fromtimestamp(visit.start)
            day = t.strftime('%Y-%m-%d')
            os.makedirs(os.path.join(self.image_dir, day), exist_ok=True)
            slug = visit.species.replace(' ', '_')
            rel = '{}/{}_{}.jpg'.format(day, t.strftime('%H%M%S'), slug)
            with open(os.path.join(self.image_dir, rel), 'wb') as f:
                f.write(jpeg_bytes)
        with self._lock:
            self._db.execute(
                'INSERT INTO visits (start, end, species, name, confidence, frames, image) VALUES (?,?,?,?,?,?,?)',
                (visit.start, visit.end, visit.species, name, visit.confidence, visit.frames, rel))
            self._db.commit()
        return rel

    def recent(self, limit=30):
        with self._lock:
            rows = self._db.execute('SELECT * FROM visits ORDER BY start DESC LIMIT ?', (limit,)).fetchall()
        return [dict(r) for r in rows]

    def counts_since(self, since_ts):
        with self._lock:
            rows = self._db.execute(
                'SELECT name, COUNT(*) AS n FROM visits WHERE start >= ? GROUP BY name ORDER BY n DESC',
                (since_ts,)).fetchall()
        return [dict(r) for r in rows]

    def hourly_since(self, since_ts):
        """Besuche je Stunde (0..23) seit since_ts."""
        hours = [0] * 24
        with self._lock:
            rows = self._db.execute('SELECT start FROM visits WHERE start >= ?', (since_ts,)).fetchall()
        for r in rows:
            hours[datetime.fromtimestamp(r['start']).hour] += 1
        return hours

    def cleanup_images(self, keep_days):
        """Loescht Bildordner, die aelter als keep_days sind (Datensaetze bleiben)."""
        limit = (datetime.now() - timedelta(days=keep_days)).strftime('%Y-%m-%d')
        for day in os.listdir(self.image_dir):
            if day < limit and os.path.isdir(os.path.join(self.image_dir, day)):
                shutil.rmtree(os.path.join(self.image_dir, day), ignore_errors=True)


def start_of_today():
    return time.mktime(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timetuple())
