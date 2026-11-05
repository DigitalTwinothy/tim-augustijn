"""Fetches open live data server-side, so visitors never call third parties from the page."""
import datetime as dt
import json
import math
import os
import urllib.request

UA = {'User-Agent': 'den-bosch-twin/1.0'}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'stad', 'data', 'live.json')
NOW = dt.datetime.now(dt.timezone.utc)


def get(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as f:
        return json.load(f)


def water():
    body = json.dumps({
        'LocatieLijst': [{'Code': 'lith.boven'}],
        'AquoPlusWaarnemingMetadataLijst': [{'AquoMetadata': {'Compartiment': {'Code': 'OW'}, 'Grootheid': {'Code': 'WATHTE'}}}],
    }).encode()
    j = get('https://ddapi20-waterwebservices.rijkswaterstaat.nl/ONLINEWAARNEMINGENSERVICES/OphalenLaatsteWaarnemingen',
            body, {'Content-Type': 'application/json'})
    best = None
    for w in j.get('WaarnemingenLijst', []):
        if w['AquoMetadata'].get('Hoedanigheid', {}).get('Code') != 'NAP':
            continue
        for m in w.get('MetingenLijst', []):
            t = dt.datetime.fromisoformat(m['Tijdstip'])
            v = m.get('Meetwaarde', {}).get('Waarde_Numeriek')
            if v is None or abs(v) > 3000:
                continue
            if best is None or t > best[0]:
                best = (t, v)
    if not best or NOW - best[0] > dt.timedelta(days=2):
        return None
    return {'plek': 'Maas bij Lith', 'nap_m': round(best[1] / 100, 2), 'tijd': best[0].isoformat()}


def weer():
    d = get('https://data.buienradar.nl/2.0/feed/json')
    for s in d['actual']['stationmeasurements']:
        if 'Volkel' in s.get('stationname', '') and s.get('temperature') is not None:
            return {'plek': 'Volkel', 'temp': s['temperature'], 'tekst': s.get('weatherdescription', ''), 'tijd': s.get('timestamp')}
    return None


def lucht():
    stations = []
    for p in range(1, 7):
        page = get(f'https://api.luchtmeetnet.nl/open_api/stations?page={p}&order_by=number')
        stations += page['data']
        if p >= page.get('pagination', {}).get('last_page', 1):
            break
    best = None
    for s in stations:
        x = get('https://api.luchtmeetnet.nl/open_api/stations/' + s['number'])['data']
        lon, lat = x['geometry']['coordinates']
        km = math.hypot((lon - 5.305) * 69, (lat - 51.69) * 111)
        if 'NO2' in (x.get('components') or []) and (best is None or km < best[0]):
            best = (km, s['number'], s['location'])
    m = get(f'https://api.luchtmeetnet.nl/open_api/measurements?station_number={best[1]}&formula=NO2&page=1&order_by=timestamp_measured&order_direction=desc')['data']
    if not m:
        return None
    return {'plek': best[2], 'km': round(best[0]), 'no2': m[0]['value'], 'tijd': m[0]['timestamp_measured']}


out = {'opgehaald': NOW.isoformat(timespec='minutes')}
for key, fn in (('water', water), ('weer', weer), ('lucht', lucht)):
    try:
        out[key] = fn()
    except Exception as e:  # one failing source must not blank the others
        print(key, 'mislukt:', repr(e)[:160])
        out[key] = None
json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False))
