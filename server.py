#!/usr/bin/env python3
"""Read-only BTC 15m Kalshi market and Coinbase spot trend dashboard."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.parse import urlparse, urlencode
from datetime import datetime, timezone
import json, os, time
HOST=os.environ.get('HOST','0.0.0.0'); PORT=int(os.environ.get('PORT','8765'))
KALSHI='https://api.elections.kalshi.com/trade-api/v2/markets'
COINBASE='https://api.exchange.coinbase.com/products/BTC-USD/candles'
def get_json(url):
    req=Request(url,headers={'User-Agent':'BTC15Signal/1.0 (read-only)','Accept':'application/json'})
    with urlopen(req,timeout=12) as r:return json.load(r)
def quote_cents(m,side):
    # Dollar fields are preferable where supplied; prices are USD per $1 contract.
    for field in (side+'_ask_dollars',side+'_ask'):
        v=m.get(field)
        if v is not None and v!='':
            try:return round(float(v)*100,1) if field.endswith('_dollars') else round(float(v),1)
            except (ValueError,TypeError):pass
    return None
def build():
    now=time.time(); out={'timestamp':int(now),'market':None,'spot':None,'trend_pct':None,'signal':'WAIT','reason':'Waiting for verified market and price data.','data_ok':False}
    errs=[]
    try:
        payload=get_json(KALSHI+'?'+urlencode({'series_ticker':'KXBTC15M','status':'open','limit':100}))
        markets=[m for m in payload.get('markets',[]) if m.get('ticker','').startswith('KXBTC15M-')]
        markets=[m for m in markets if (datetime.fromisoformat(m['close_time'].replace('Z','+00:00')).timestamp()>now+5) and (not m.get('open_time') or datetime.fromisoformat(m['open_time'].replace('Z','+00:00')).timestamp()<=now)]
        markets.sort(key=lambda m:m['close_time'])
        if markets:
            m=markets[0]
            out['market']={'ticker':m['ticker'],'title':m.get('title'),'close_time':m['close_time'],'yes_ask':quote_cents(m,'yes'),'no_ask':quote_cents(m,'no'),'url':'https://kalshi.com/markets/'+m['ticker'].split('-')[0].lower()+'/'+m.get('event_ticker',m['ticker']).lower()}
        else:errs.append('No currently trading BTC 15-minute market returned by Kalshi.')
    except Exception as e:errs.append('Kalshi feed unavailable: '+str(e)[:120])
    try:
        candles=get_json(COINBASE+'?'+urlencode({'granularity':60}))
        candles=sorted((c for c in candles if isinstance(c,list) and len(c)>=5),key=lambda c:c[0])
        if len(candles)<12:raise ValueError('Not enough recent candles')
        latest=candles[-1]; earlier=min(candles,key=lambda c:abs(c[0]-(latest[0]-600)))
        spot=float(latest[4]); old=float(earlier[4]); pct=(spot/old-1)*100
        out['spot']=round(spot,2);out['trend_pct']=round(pct,3)
    except Exception as e:errs.append('BTC price feed unavailable: '+str(e)[:120])
    m=out['market']; pct=out['trend_pct']
    if m and pct is not None:
        remaining=datetime.fromisoformat(m['close_time'].replace('Z','+00:00')).timestamp()-now
        if remaining<120:out['reason']='Less than 2 minutes remain. Avoid late entries.'
        elif abs(pct)<0.20:out['reason']='10-minute Bitcoin movement is too small for this momentum rule.'
        else:
            side='UP' if pct>0 else 'DOWN'; ask=m['yes_ask' if side=='UP' else 'no_ask']
            if ask is None:out['reason']='Live ask price is unavailable; no signal.'
            elif ask>65:out['reason']=f'{side} costs {ask}¢; price is above the 65¢ safety cutoff.'
            elif ask<=0:out['reason']='Market price is invalid; no signal.'
            else:
                out['signal']=side
                out['reason']=f'10-minute spot momentum is {pct:+.3f}% and {side} ask is {ask}¢. Heuristic only; no proven edge.'
        out['data_ok']=True
    if errs:out['warnings']=errs
    return out
class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/signal':
            try:result=build();status=200
            except Exception as e:result={'signal':'WAIT','reason':'Server error: '+str(e)[:100],'data_ok':False};status=502
            body=json.dumps(result).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        if path not in ('/','/index.html'):self.send_error(404);return
        self.path='/index.html';super().do_GET()
if __name__=='__main__':ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
