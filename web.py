"""Kleine Webseite: letzte Besucher mit Foto, Tagesstatistik und Livebild."""

import threading
import time
from datetime import datetime

from flask import Flask, Response, abort, jsonify, render_template_string, send_from_directory

from storage import start_of_today

PAGE = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>Vogelwacht</title>
<style>
  :root { --bg:#f6f4ee; --card:#fff; --text:#222; --muted:#777; --accent:#3a7d44; }
  @media (prefers-color-scheme: dark) { :root { --bg:#1b1d1a; --card:#262924; --text:#eee; --muted:#999; --accent:#7cc487; } }
  body { margin:0; font-family:system-ui,sans-serif; background:var(--bg); color:var(--text); }
  main { max-width:960px; margin:0 auto; padding:16px; }
  h1 { margin:0 0 4px; } .muted { color:var(--muted); }
  section { background:var(--card); border-radius:10px; padding:16px; margin:16px 0; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:12px; }
  .visit img { width:100%; aspect-ratio:4/3; object-fit:cover; border-radius:6px; background:#0002; }
  .visit b { display:block; margin-top:4px; }
  .bar { display:flex; align-items:center; gap:8px; margin:4px 0; }
  .bar span:first-child { width:140px; } .bar i { background:var(--accent); height:12px; border-radius:3px; }
  .hours { display:flex; align-items:flex-end; gap:2px; height:80px; }
  .hours div { flex:1; background:var(--accent); border-radius:2px 2px 0 0; min-height:1px; }
  .live { width:100%; max-width:480px; border-radius:6px; }
</style>
</head>
<body><main>
<h1>Vogelwacht</h1>
<div class="muted">Stand {{ now }} · {{ status }}</div>

<section>
<h2>Heute</h2>
{% if counts %}
  {% for c in counts %}
  <div class="bar"><span>{{ c.name }}</span><i style="width:{{ (c.n * 200 // max_count) }}px"></i><span>{{ c.n }}</span></div>
  {% endfor %}
  <h3>Besuche nach Uhrzeit</h3>
  <div class="hours">{% for h in hours %}<div title="{{ loop.index0 }} Uhr: {{ h }}" style="height:{{ (h * 100 // max_hour) }}%"></div>{% endfor %}</div>
  <div class="muted">0 Uhr – 23 Uhr</div>
{% else %}
  <p class="muted">Heute noch kein Besuch.</p>
{% endif %}
</section>

<section>
<h2>Letzte Besucher</h2>
<div class="grid">
{% for v in visits %}
  <div class="visit">
    {% if v.image %}<img src="/img/{{ v.image }}" alt="{{ v.name }}" loading="lazy">{% endif %}
    <b>{{ v.name }}</b>
    <span class="muted">{{ v.time }} · {{ v.conf }} % · {{ v.frames }} Bilder</span>
  </div>
{% else %}
  <p class="muted">Noch keine Besuche gespeichert.</p>
{% endfor %}
</div>
</section>

<section>
<h2>Livebild</h2>
<img class="live" src="/live.jpg?t={{ ts }}" alt="Livebild">
</section>
</main></body></html>
"""


class SharedState:
    """Vom Hauptprogramm befuellt, von der Webseite gelesen."""

    def __init__(self):
        self._lock = threading.Lock()
        self.live_jpeg = None
        self.status = 'startet'

    def set_live(self, jpeg):
        with self._lock:
            self.live_jpeg = jpeg

    def get_live(self):
        with self._lock:
            return self.live_jpeg


def create_app(storage, state):
    app = Flask(__name__)

    @app.route('/')
    def index():
        today = start_of_today()
        counts = storage.counts_since(today)
        hours = storage.hourly_since(today)
        visits = []
        for v in storage.recent(30):
            visits.append(dict(v, time=datetime.fromtimestamp(v['start']).strftime('%d.%m. %H:%M'),
                               conf=round(v['confidence'] * 100)))
        return render_template_string(
            PAGE, now=datetime.now().strftime('%d.%m.%Y %H:%M'), status=state.status,
            counts=counts, max_count=max([c['n'] for c in counts] or [1]),
            hours=hours, max_hour=max(hours) or 1, visits=visits, ts=int(time.time()))

    @app.route('/img/<path:rel>')
    def image(rel):
        return send_from_directory(storage.image_dir, rel)

    @app.route('/live.jpg')
    def live():
        jpeg = state.get_live()
        if jpeg is None:
            abort(404)
        return Response(jpeg, mimetype='image/jpeg', headers={'Cache-Control': 'no-store'})

    @app.route('/api/visits')
    def api_visits():
        return jsonify(storage.recent(100))

    return app


def start_web(storage, state, host, port):
    app = create_app(storage, state)
    t = threading.Thread(target=lambda: app.run(host=host, port=port, threaded=True, use_reloader=False),
                         daemon=True, name='web')
    t.start()
    return t
