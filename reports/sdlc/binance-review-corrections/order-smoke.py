import json, os, sqlite3, ssl, subprocess, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from tests.test_binance_trading import EXCHANGE_INFO, PREMIUM

repo=Path.cwd(); requests=[]
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  assert not self.headers.get('X-MBX-APIKEY')
  requests.append(urlsplit(self.path).path)
  data=EXCHANGE_INFO if requests[-1]=='/fapi/v1/exchangeInfo' else PREMIUM
  self.send_response(200);self.end_headers();self.wfile.write(data.encode())
 def do_POST(self):raise AssertionError('dry-run sent POST')
 def do_DELETE(self):raise AssertionError('dry-run sent DELETE')
with tempfile.TemporaryDirectory() as td:
 t=Path(td);cert=t/'cert.pem';key=t/'key.pem';db=t/'smoke.sqlite'
 subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(cert,key);server.socket=ctx.wrap_socket(server.socket,server_side=True)
 threading.Thread(target=server.serve_forever,daemon=True).start()
 env={'PATH':os.environ['PATH'],'PYTHONPATH':str(repo),'SSL_CERT_FILE':str(cert),'BINANCE_BASE_URL':f'https://localhost:{server.server_port}','BINANCE_APIKEY':'','BINANCE_SECRET':''}
 cases=[['binance-trade','--symbol','BTCUSDT','--side','buy','--order-type','limit','--quantity','.0104','--price','75000.07'],['binance-stop','--symbol','BTCUSDT','--side','sell','--kind','stop-market','--stop-price','74000'],['binance-stop','--symbol','BTCUSDT','--side','sell','--kind','trailing','--quantity','.01','--callback-rate','1.5'],['binance-cancel','--symbol','BTCUSDT','--algo-id','7']]
 try:
  for argv in cases:
   result=subprocess.run([str(repo/'.venv/bin/python'),'-m','kis_hl.cli','--db',str(db),*argv,'--dry-run'],cwd=t,env=env,text=True,capture_output=True)
   assert result.returncode==0,result.stderr
   data=json.loads(result.stdout);assert data['status']=='dry_run' and data['dry_run']
  with sqlite3.connect(db) as conn:
   assert conn.execute('select count(*) from order_submissions').fetchone()[0]==4
   assert conn.execute('select count(*) from protective_orders where active=1').fetchone()[0]==0
  print(json.dumps({'result':'PASS','commands':4,'real_https_public_reads':len(requests),'signed_calls':0,'stored_submissions':4,'active_protection':0}))
 finally:server.shutdown();server.server_close()
