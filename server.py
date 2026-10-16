#!/usr/bin/env python3
"""Small local static server + allowlisted public Kalshi API proxy (no credentials)."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.parse import urlparse, parse_qs, urlencode
import json
import os

HOST=os.environ.get('HOST','127.0.0.1'); PORT=int(os.environ.get('PORT','8765'))
UPSTREAM='https://api.elections.kalshi.com/trade-api/v2/markets'
class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        p=urlparse(self.path)
        if p.path!='/api/markets':
            return super().do_GET()
        query=parse_qs(p.query)
        args={'limit':min(200,max(1,int(query.get('limit',['200'])[0]))),'status':'open'}
        if query.get('cursor'):args['cursor']=query['cursor'][0][:500]
        try:
            req=Request(UPSTREAM+'?'+urlencode(args),headers={'User-Agent':'KalshiValueFinder/1.0','Accept':'application/json'})
            with urlopen(req,timeout=18) as response:
                data=response.read(5_000_000)
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
        except Exception as e:
            data=json.dumps({'error':str(e)}).encode()
            self.send_response(502);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(data)
if __name__=='__main__':
    print(f'Open http://{HOST}:{PORT} in your browser')
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
