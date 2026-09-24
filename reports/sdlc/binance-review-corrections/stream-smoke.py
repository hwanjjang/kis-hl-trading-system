import base64, hashlib, json, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from kis_hl.binance.client import BinanceFuturesClient
from kis_hl.binance.ws import BinanceUserStreamClient, parse_order_event, order_event_to_row
from kis_hl.config import BinanceConfig
from kis_hl.storage import store_order_event, list_order_events

calls=[]
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        calls.append('create'); self.send_response(200); self.end_headers(); self.wfile.write(b'{"listenKey":"local-smoke-key"}')
    def do_PUT(self):
        calls.append('renew'); self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
    def do_GET(self):
        accept=base64.b64encode(hashlib.sha1((self.headers['Sec-WebSocket-Key']+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        self.send_response(101); self.send_header('Upgrade','websocket'); self.send_header('Connection','Upgrade'); self.send_header('Sec-WebSocket-Accept',accept); self.end_headers()
        time.sleep(.3)
        data=json.dumps({'e':'ORDER_TRADE_UPDATE','E':1,'o':{'s':'BTCUSDT','i':7,'X':'FILLED'}}).encode()
        self.wfile.write(bytes([0x81,len(data)])+data); self.wfile.flush(); time.sleep(.1)
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
port=server.server_port
cfg=BinanceConfig(f'http://127.0.0.1:{port}', '', '', f'ws://127.0.0.1:{port}', 'local-dummy', '', 'default')
try:
 with tempfile.TemporaryDirectory() as tmp:
    db=Path(tmp)/'smoke.sqlite'
    def receive(payload):
        event=parse_order_event(payload,received_at_ms=2)
        store_order_event(db,**order_event_to_row(event))
    client=BinanceUserStreamClient(cfg,BinanceFuturesClient(cfg),on_message=receive,keepalive_interval_ms=50,recv_timeout_seconds=.1)
    status=client.run(max_messages=1,max_reconnects=0)
    assert status.connection_count==1 and status.reconnect_count==0, status
    assert calls.count('create')==1 and 'renew' in calls, calls
    assert list_order_events(db)[0]['status']=='FILLED'
    print(json.dumps({'result':'PASS','real_loopback_websocket':True,'real_REST':True,'sqlite_event':'FILLED','renewals':calls.count('renew')}))
finally: server.shutdown(); server.server_close()
