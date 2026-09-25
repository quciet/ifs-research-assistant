"""Isolated browser fixture for provider/model selection; never calls a real provider."""
import json
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from ifs_agent.catalog import PRESETS
from ifs_agent.webapp import Application,make_server

class Models(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        data=json.dumps({'data':[{'id':'fixture-flash'},{'id':'fixture-pro'}]}).encode()
        self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    mock=ThreadingHTTPServer(('127.0.0.1',8767),Models)
    threading.Thread(target=mock.serve_forever,daemon=True).start()
    PRESETS['deepseek']={**PRESETS['deepseek'],'label':'DeepSeek (local test fixture)','endpoint':'http://127.0.0.1:8767'}
    app=Application(root);app.root=root/'workspace/provider-ui-test';app.root.mkdir(parents=True,exist_ok=True)
    app.path=app.root/'settings.json';app.artifacts=app.root/'artifacts'
    server=make_server(app,8766)
    print('Provider dropdown fixture: http://127.0.0.1:8766',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();mock.shutdown();mock.server_close()
