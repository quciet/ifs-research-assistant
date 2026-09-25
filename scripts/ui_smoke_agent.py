"""Local, simulated-provider UI smoke fixture. No real LLM or credentials involved."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from ifs_agent.webapp import Application,make_server

class Mock(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        calls=sum(x.get('type')=='function_call_output' for x in body['input'])
        steps=[('source_status',{}),('code_read',{'path':'Models/Economy.Forecast.vb','start':13620,'end':13665}),
               ('equality',{'dataset':'IFsBase','x':'I','y':'INVS','first_year':2022,'last_year':2023,'atol':.001,'rtol':.000001})]
        if calls<len(steps):
            name,args=steps[calls]
            output=[{'type':'function_call','call_id':str(calls),'name':name,'arguments':json.dumps(args)}]
        else:output=[{'type':'message','role':'assistant','content':[{'type':'output_text','text':'SIMULATED PROVIDER TEST — not a live model answer.\n\nThe browser sent tool requests and received actual local evidence. Inspect the code and equality artifacts in the evidence panel. The calculation alone does not establish an equality requirement or a model bug.'}]}]
        data=json.dumps({'status':'completed','output':output}).encode();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)

if __name__=='__main__':
    project=Path(__file__).resolve().parents[1]
    app=Application(project)
    app.root=project/'workspace/ui-smoke';app.root.mkdir(parents=True,exist_ok=True)
    app.path=app.root/'settings.json';app.artifacts=app.root/'artifacts'
    provider=ThreadingHTTPServer(('127.0.0.1',8767),Mock)
    threading.Thread(target=provider.serve_forever,daemon=True).start()
    app.settings={'protocol':'responses','endpoint':'http://127.0.0.1:8767/v1','model':'SIMULATED-UI-TEST','source_folder':'','config':str(project/'resources/research.json')}
    server=make_server(app,8766)
    print('Simulated-provider UI test: http://127.0.0.1:8766',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:app.cancel();server.server_close();provider.shutdown();provider.server_close()
