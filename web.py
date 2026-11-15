"""Kleine Webseite: letzte Besucher mit Foto, Tagesstatistik und Livebild.
Sprache aus config.toml ([ui] language), umschaltbar per Link (?lang=de / ?lang=en)."""

import threading
import time
from datetime import datetime

from flask import Flask, Response, abort, jsonify, render_template_string, request, send_from_directory

from species_de import bird_name
from storage import start_of_today

TEXTS = {
    'de': {
        'updated': 'Stand', 'today': 'Heute', 'by_hour': 'Besuche nach Uhrzeit',
        'hours': '0 Uhr – 23 Uhr', 'hour_tip': '{h} Uhr: {n}', 'no_visit_today': 'Heute noch kein Besuch.',
        'recent': 'Letzte Besucher', 'frames': 'Bilder', 'no_visits': 'Noch keine Besuche gespeichert.',
        'live': 'Livebild', 'live_alt': 'Livebild',
        'date_now': '%d.%m.%Y %H:%M', 'date_visit': '%d.%m. %H:%M',
        'starting': 'startet', 'night': 'Nachtpause', 'waiting': 'wartet auf Bewegung',
        'watching': 'beobachtet', 'bird': 'Vogel: {name}',
    },
    'en': {
        'updated': 'Updated', 'today': 'Today', 'by_hour': 'Visits by time of day',
        'hours': '0:00 – 23:00', 'hour_tip': '{h}:00: {n}', 'no_visit_today': 'No visits yet today.',
        'recent': 'Recent visitors', 'frames': 'frames', 'no_visits': 'No visits stored yet.',
        'live': 'Live image', 'live_alt': 'Live image',
        'date_now': '%Y-%m-%d %H:%M', 'date_visit': '%d %b, %H:%M',
        'starting': 'starting', 'night': 'night pause', 'waiting': 'waiting for motion',
        'watching': 'watching', 'bird': 'Bird: {name}',
    },
}
LANGS = tuple(TEXTS)

PAGE = """<!doctype html>
<html lang="{{ lang }}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30;url=/?lang={{ lang }}">
<title>Vogelwacht</title>
<style>
  :root { --bg:#f6f4ee; --card:#fff; --text:#222; --muted:#777; --accent:#3a7d44; }
  @media (prefers-color-scheme: dark) { :root { --bg:#1b1d1a; --card:#262924; --text:#eee; --muted:#999; --accent:#7cc487; } }
  body { margin:0; font-family:system-ui,sans-serif; background:var(--bg); color:var(--text); }
  main { max-width:960px; margin:0 auto; padding:16px; }
  header { display:flex; justify-content:space-between; align-items:baseline; gap:12px; }
  h1 { margin:0 0 4px; } .muted { color:var(--muted); }
  .lang a { color:var(--muted); text-decoration:none; padding:2px 6px; border-radius:4px; }
  .lang a.on { color:var(--text); background:var(--card); font-weight:600; }
  section { background:var(--card); border-radius:10px; padding:16px; margin:16px 0; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:12px; }
  .visit img { width:100%; aspect-ratio:4/3; object-fit:cover; border-radius:6px; background:#0002; }
  .visit b { display:block; margin-top:4px; }
  .bar { display:flex; align-items:center; gap:8px; margin:4px 0; }
  .bar span:first-child { width:190px; } .bar i { background:var(--accent); height:12px; border-radius:3px; }
  .hours { display:flex; align-items:flex-end; gap:2px; height:80px; }
  .hours div { flex:1; background:var(--accent); border-radius:2px 2px 0 0; min-height:1px; }
  .live { width:100%; max-width:480px; border-radius:6px; }
</style>
</head>
<body><main>
<header>
  <h1>Vogelwacht</h1>
  <nav class="lang">{% for l in langs %}<a href="/?lang={{ l }}" class="{{ 'on' if l == lang }}">{{ l|upper }}</a>{% endfor %}</nav>
</header>
<div class="muted">{{ t.updated }} {{ now }} · {{ status }}</div>

<section>
<h2>{{ t.today }}</h2>
{% if counts %}
  {% for c in counts %}
  <div class="bar"><span>{{ c.name }}</span><i style="width:{{ (c.n * 200 // max_count) }}px"></i><span>{{ c.n }}</span></div>
  {% endfor %}
  <h3>{{ t.by_hour }}</h3>
  <div class="hours">{% for h in hours %}<div title="{{ t.hour_tip.format(h=loop.index0, n=h) }}" style="height:{{ (h * 100 // max_hour) }}%"></div>{% endfor %}</div>
  <div class="muted">{{ t.hours }}</div>
{% else %}
  <p class="muted">{{ t.no_visit_today }}</p>
{% endif %}
</section>

<section>
<h2>{{ t.recent }}</h2>
<div class="grid">
{% for v in visits %}
  <div class="visit">
    {% if v.image %}<img src="/img/{{ v.image }}" alt="{{ v.name }}" loading="lazy">{% endif %}
    <b>{{ v.name }}</b>
    <span class="muted">{{ v.time }} · {{ v.conf }} % · {{ v.frames }} {{ t.frames }}</span>
  </div>
{% else %}
  <p class="muted">{{ t.no_visits }}</p>
{% endfor %}
</div>
</section>

<section>
<h2>{{ t.live }}</h2>
<img class="live" src="/live.jpg?t={{ ts }}" alt="{{ t.live_alt }}">
</section>
</main></body></html>
"""


class SharedState:
    """Vom Hauptprogramm befuellt, von der Webseite gelesen. Der Status ist ein
    Schluessel aus TEXTS ('night', 'waiting', 'watching', 'bird'), bei 'bird'
    zusammen mit dem lateinischen Namen; die Webseite uebersetzt ihn."""

    def __init__(self):
        self._lock = threading.Lock()
        self.live_jpeg = None
        self.status = 'starting'
        self.status_species = None

    def set_status(self, key, species=None):
        self.status, self.status_species = key, species

    def set_live(self, jpeg):
        with self._lock:
            self.live_jpeg = jpeg

    def get_live(self):
        with self._lock:
            return self.live_jpeg


def status_text(state, lang):
    t = TEXTS[lang]
    key = state.status if state.status in t else 'starting'
    if key == 'bird':
        return t['bird'].format(name=bird_name(state.status_species, lang))
    return t[key]


def create_app(storage, state, language='de'):
    app = Flask(__name__)
    default = language if language in TEXTS else 'de'

    @app.route('/')
    def index():
        lang = request.args.get('lang', default)
        if lang not in TEXTS:
            lang = default
        t = TEXTS[lang]
        today = start_of_today()
        counts = [dict(c, name=bird_name(c['species'], lang, c['name']))
                  for c in storage.counts_since(today)]
        hours = storage.hourly_since(today)
        visits = []
        for v in storage.recent(30):
            visits.append(dict(v, name=bird_name(v['species'], lang, v['name']),
                               time=datetime.fromtimestamp(v['start']).strftime(t['date_visit']),
                               conf=round(v['confidence'] * 100)))
        return render_template_string(
            PAGE, lang=lang, langs=LANGS, t=t, now=datetime.now().strftime(t['date_now']),
            status=status_text(state, lang),
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


def start_web(storage, state, host, port, language='de'):
    app = create_app(storage, state, language)
    t = threading.Thread(target=lambda: app.run(host=host, port=port, threaded=True, use_reloader=False),
                         daemon=True, name='web')
    t.start()
    return t
