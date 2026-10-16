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
COINBASE_ADV='https://api.coinbase.com/api/v3/brokerage/market/products/BTC-USD/candles'
KRAKEN='https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1'
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
def minute_history(now):
    """Fetch 1m candles from independent providers, without mixing sources."""
    errors=[]
    sources=[
        ('Coinbase Exchange', COINBASE+'?'+urlencode({'granularity':60,'start':datetime.fromtimestamp(now-1800, __import__('datetime').timezone.utc).isoformat(),'end':datetime.fromtimestamp(now+60, __import__('datetime').timezone.utc).isoformat()})),
        ('Coinbase Advanced', COINBASE_ADV+'?'+urlencode({'start':int(now-1800),'end':int(now+60),'granularity':'ONE_MINUTE','limit':35})),
        ('Kraken', KRAKEN),
    ]
    for name,url in sources:
        try:
            data=fetch(url)
            if name=='Coinbase Exchange':
                rows={int(c[0]):float(c[4]) for c in data if isinstance(c,list) and len(c)>4}
            elif name=='Coinbase Advanced':
                rows={int(c['start']):float(c['close']) for c in data.get('candles',[])}
            else:
                if data.get('error'):raise ValueError(str(data['error']))
                values=next(v for k,v in data['result'].items() if k!='last')
                rows={int(c[0]):float(c[4]) for c in values if len(c)>4}
            rows={t:v for t,v in rows.items() if math.isfinite(v) and v>0 and t<=now+60}
            if len(rows)<11:raise ValueError('fewer than 11 one-minute candles')
            latest=max(rows)
            # A candle's timestamp is its START; current candle can be up to 60s old.
            if now-latest>150:raise ValueError('latest candle is stale')
            # Only use minute-aligned exact historical candles, no approximations.
            for n in (1,5,10):
                if latest-n*60 not in rows:raise ValueError(f'missing {n}-minute reference candle')
            spot=rows[latest]
            trends={str(n):round((spot/rows[latest-n*60]-1)*100,4) for n in (1,5,10)}
            return round(spot,2),trends,name,errors
        except Exception as e:
            errors.append(name+': '+str(e)[:110])
    return None,{},None,errors

def build():
    now=time.time(); result={'timestamp':int(now),'signal':'WAIT','reason':'Checking feeds','spot':None,'trends':{},'market':None,'checks':[],'warnings':[],'data_ok':False,'rule_version':'v3.0','price_source':None,'feed_status':{}}
    try:
        data=fetch(KALSHI+'?'+urlencode({'series_ticker':'KXBTC15M','status':'open','limit':100}))
        markets=[m for m in data.get('markets',[]) if m.get('ticker','').startswith('KXBTC15M-') and m.get('close_time') and ts(m['close_time'])>now+5 and (not m.get('open_time') or ts(m['open_time'])<=now)]
        markets.sort(key=lambda m:ts(m['close_time']))
        if markets:
            m=markets[0];result['market']={'ticker':m['ticker'],'title':m.get('title'),'close_time':m['close_time'],'yes_ask':ask(m,'yes'),'no_ask':ask(m,'no'),'url':'https://kalshi.com/markets/'+m['ticker'].split('-')[0].lower()+'/'+m.get('event_ticker',m['ticker']).lower()}
            result['feed_status']['kalshi']='OK'
        else:
            result['feed_status']['kalshi']='No open BTC 15m market';result['warnings'].append('No active 15-minute Kalshi BTC market returned.')
    except Exception as e:
        result['feed_status']['kalshi']='Error';result['warnings'].append('Kalshi feed: '+str(e)[:130])
    spot,trends,source,errors=minute_history(now)
    result['spot']=spot;result['trends']=trends;result['price_source']=source
    result['feed_status']['bitcoin']=source or 'Unavailable'
    if source and errors:result['warnings'].append('Backup feed used; earlier sources failed: '+'; '.join(errors))
    if not source:result['warnings'].extend(errors)
    m=result['market'];t=result['trends']
    if not m or len(t)!=3:
        result['reason']='Market or Bitcoin minute-history feed unavailable. No signal.'
        result['checks']=['Kalshi: '+result['feed_status'].get('kalshi','Unknown'),'Bitcoin history: '+result['feed_status']['bitcoin']]
        return result
    result['data_ok']=True
    remaining=ts(m['close_time'])-now
    result['checks'].append(f'{int(remaining//60)}m {int(remaining%60)}s remaining')
    if remaining<120:
        result['reason']='Less than 2 minutes left in this market.';return result
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
