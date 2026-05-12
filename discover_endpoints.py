import http.client
import json

headers = {
    'x-rapidapi-key': 'f4847705f4msh2a3160f9508003dp1575a8jsnc195177821ee',
    'x-rapidapi-host': 'yahoo-finance166.p.rapidapi.com'
}

tests = [
    '/api/stock/get-financial-data?region=ID&symbol=BBCA.JK',
    '/api/stock/get-statistics?region=ID&symbol=BBCA.JK',
    '/api/stock/get-price?region=ID&symbol=BBCA.JK',
    '/api/stock/get-fundamentals?region=ID&symbol=BBCA.JK',
    '/api/stock/get-chart?symbol=BBCA.JK&interval=1d&range=1y&region=ID',
    '/api/stock/get-earnings?symbol=BBCA.JK&region=ID',
    '/api/stock/get-timeseries?symbol=BBCA.JK&region=ID',
    '/api/screeners/screenerList?scrIds=undervalued_growth_stocks&count=25',
    '/api/screener/screenerGetPredefinedScreener?scrIds=undervalued_growth_stocks',
]

for ep in tests:
    c = http.client.HTTPSConnection('yahoo-finance166.p.rapidapi.com')
    c.request('GET', ep, headers=headers)
    r = c.getresponse()
    raw = r.read().decode('utf-8')
    short_ep = ep.split('?')[0]
    print(f'[HTTP {r.status}] {short_ep}')
    if r.status == 200:
        data = json.loads(raw)
        print(json.dumps(data, indent=2)[:800])
    print()
