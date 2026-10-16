#!/usr/bin/env python3
"""Read-only, experimental BTC 15m directional dashboard."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.parse import urlparse, urlencode
from datetime import datetime
import json, os, time, math
HOST=os.environ.get('HOST','0.0.0.0'); PORT=int(os.environ.get('PORT','8765'))
KALSHI='https://api.elections.kalshi.com/trade-api/v2/markets'
COINBASE='https://api.exchange.coinbase.com/products/BTC-USD/candles'
def fetch(url):
    with urlopen(Request(url,headers={'User-Agent':'BTC15Signal/2.0','Accept':'application/json'}),timeout=12) as r:return json.load(r)
def ts(s):return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
def ask(m,side):
    for field in (side+'_ask_dollars',side+'_ask'):
        v=m.get(field)
        try:
            if v is not None and v!='':
                n=float(v)*(100 if field.endswith('_dollars') else 1)
                if math.isfinite(n) and 0<n<=100:return round(n,1)
        except (ValueError,TypeError):pass
    return None
def build():
    now=time.time(); result={'timestamp':int(now),'signal':'WAIT','reason':'Checking feeds','spot':None,'trends':{},'market':None,'checks':[],'warnings':[],'data_ok':False,'rule_version':'v2.0'}
    try:
        data=fetch(KALSHI+'?'+urlencode({'series_ticker':'KXBTC15M','status':'open','limit':100}))
        markets=[m for m in data.get('markets',[]) if m.get('ticker','').startswith('KXBTC15M-') and m.get('close_time') and ts(m['close_time'])>now+5 and (not m.get('open_time') or ts(m['open_time'])<=now)]
        markets.sort(key=lambda m:ts(m['close_time']))
        if markets:
            m=markets[0];result['market']={'ticker':m['ticker'],'title':m.get('title'),'close_time':m['close_time'],'yes_ask':ask(m,'yes'),'no_ask':ask(m,'no'),'url':'https://kalshi.com/markets/'+m['ticker'].split('-')[0].lower()+'/'+m.get('event_ticker',m['ticker']).lower()}
        else:result['warnings'].append('No active 15-minute Kalshi BTC market returned.')
    except Exception as e:result['warnings'].append('Kalshi feed: '+str(e)[:130])
    try:
        candles=fetch(COINBASE+'?'+urlencode({'granularity':60}))
        rows={int(c[0]):float(c[4]) for c in candles if isinstance(c,list) and len(c)>=5 and float(c[4])>0}
        if len(rows)<12:raise ValueError('Insufficient minute candles')
        latest=max(rows);spot=rows[latest]
        if now-latest>180:raise ValueError('Coinbase candles are stale')
        for minutes in (1,5,10):
            target=latest-minutes*60
            candidates=[t for t in rows if abs(t-target)<=65]
            if not candidates:raise ValueError(f'Missing {minutes}-minute history')
            t=min(candidates,key=lambda t:abs(t-target));result['trends'][str(minutes)]=round((spot/rows[t]-1)*100,4)
        result['spot']=round(spot,2)
    except Exception as e:result['warnings'].append('Coinbase feed: '+str(e)[:130])
    m=result['market'];t=result['trends']
    if not m or len(t)!=3:
        result['reason']='Market or price history unavailable. No signal.'
        result['checks']=['Waiting for verified live feeds']
        return result
    result['data_ok']=True
    remaining=ts(m['close_time'])-now
    result['checks'].append(f'{int(remaining//60)}m {int(remaining%60)}s remaining')
    if remaining<120:
        result['reason']='Less than 2 minutes left in this market.';return result
    # Experimental, transparent trend classifier; not a probability or expected-value model.
    # Require medium and longer horizon agreement, plus a modest short-term confirmation.
    t1,t5,t10=t['1'],t['5'],t['10']
    result['checks'].append(f'1m {t1:+.4f}% · 5m {t5:+.4f}% · 10m {t10:+.4f}%')
    if abs(t5)<0.025 or abs(t10)<0.04:
        result['reason']='5-minute or 10-minute movement is too small for this rule.';return result
    direction=1 if t5>0 else -1
    if t10*direction<=0 or t1*direction< -0.012:
        result['reason']='Short, medium and longer trends do not agree.';return result
    side='UP' if direction>0 else 'DOWN'
    price=m['yes_ask' if direction>0 else 'no_ask']
    result['checks'].append(f'{side} ask: {price}¢' if price is not None else f'{side} ask unavailable')
    if price is None:
        result['reason']='Matching Kalshi ask is unavailable.';return result
    if price>65:
        result['reason']=f'{side} ask is {price}¢, above the 65¢ display cutoff.';return result
    result['signal']=side
    result['reason']=f'{side} trend observed across 5m and 10m, with 1m confirmation. Not a verified betting edge.'
    return result
class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/signal':
            try:body=json.dumps(build()).encode();status=200
            except Exception as e:body=json.dumps({'signal':'WAIT','reason':'Server error','warnings':[str(e)[:130]],'data_ok':False}).encode();status=502
            self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        if path not in ('/','/index.html'):self.send_error(404);return
        self.path='/index.html';super().do_GET()
if __name__=='__main__':ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
