from __future__ import annotations
import json
import multiprocessing as mp
import queue
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4
from .provider import validate_settings
from .catalog import PRESETS, list_models
from .agent import worker, source_worker
from .tools import ToolService
from .sources import connect
from .processes import own_process, stop_process


class Application:
    def __init__(self, project):
        self.project=Path(project).resolve()
        self.root=self.project/'workspace/agent'
        self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'settings.json'
        self.settings={'protocol':'responses','endpoint':'https://api.openai.com/v1','model':'',
                       'source_folder':'','config':str(self.project/'resources/research.json')}
        if self.path.exists(): self.settings.update(json.loads(self.path.read_text(encoding='utf-8')))
        self.key=''; self.token=secrets.token_urlsafe(32); self.lock=threading.RLock()
        self.job=None; self.process=None; self.events=[]; self.history=[]
        self.artifacts=self.root/'artifacts'
        self.jobs={}

    def status(self):
        try: sources=ToolService(self.settings['config'],self.artifacts).call('source_status',{})
        except Exception as exc: sources={'unavailable':str(exc),'notice':'Select your IFs development folder in Settings.'}
        return {'settings':{k:v for k,v in self.settings.items() if k!='config'},'key_present':bool(self.key),
                'presets':PRESETS,'sources':sources,'busy':bool(self.process and self.process.is_alive())}

    def models(self, data):
        # Discovery never persists a key or modifies the active connection.
        connection=validate_settings({**data,'model':'discovery'})
        with self.lock:
            if not connection['api_key'] and not data.get('clear_key'):
                if all(connection[k]==self.settings[k] for k in ('endpoint','protocol')):
                    connection['api_key']=self.key
        return list_models(connection)

    def save(self, data):
        with self.lock:
            if self.process and self.process.is_alive(): raise ValueError('Cancel or finish the active investigation before changing settings')
            settings=validate_settings(data)
            key=settings.pop('api_key')
            folder=data.get('source_folder','').strip()
            config=self.settings['config']
            if folder and folder!=self.settings.get('source_folder'):
                config=connect(self.project,folder)
            if not Path(config).is_file(): raise ValueError('Select an IFs development folder')
            previous_endpoint=self.settings['endpoint']
            previous_protocol=self.settings['protocol']
            self.settings={**settings,'source_folder':folder,'config':config}
            self.key=key if key else ('' if data.get('clear_key') or settings['endpoint']!=previous_endpoint or settings['protocol']!=previous_protocol else self.key)
            temp=self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(self.settings,indent=2),encoding='utf-8')
            temp.replace(self.path)
            self.history=[]
            return self.status()

    def start(self, question):
        with self.lock:
            if not isinstance(question,str) or not question.strip() or len(question)>10000:
                raise ValueError('Enter a question of 1 to 10,000 characters')
            if self.process and self.process.is_alive(): raise ValueError('An investigation is already running')
            settings=validate_settings({**self.settings,'api_key':self.key})
            self.job=uuid4().hex; self.events=[]
            self.log=self.root/'conversations'/(self.job+'.jsonl')
            self.log.parent.mkdir(parents=True,exist_ok=True)
            context=mp.get_context('spawn'); q=context.Queue()
            self.process=context.Process(target=worker,args=(settings,self.settings['config'],str(self.artifacts),
                question,list(self.history),q,str(self.log)),daemon=False)
            self.process.start()
            self.jobs[self.process.pid]=own_process(self.process)
            threading.Thread(target=self.monitor,args=(self.process,q,question),daemon=True).start()
            return {'job':self.job}

    def refresh(self, kind):
        if kind not in ('code','wiki'): raise ValueError('Unknown source refresh')
        with self.lock:
            if self.process and self.process.is_alive(): raise ValueError('Finish or cancel the active investigation first')
            self.job=uuid4().hex; self.events=[]; self.history=[]
            self.log=self.root/'conversations'/(self.job+'.jsonl')
            self.log.parent.mkdir(parents=True,exist_ok=True)
            context=mp.get_context('spawn'); q=context.Queue()
            self.process=context.Process(target=source_worker,args=(self.settings['config'],kind,q,str(self.log)))
            self.process.start()
            self.jobs[self.process.pid]=own_process(self.process)
            threading.Thread(target=self.monitor,args=(self.process,q,''),daemon=True).start()
            return {'job':self.job}

    def monitor(self, process, q, question):
        started=time.monotonic(); answer=None; finished=False
        while process.is_alive() or not finished:
            try:
                event=q.get(timeout=.2)
                with self.lock:
                    if process is not self.process or any(e.get('status')=='cancelled' for e in self.events): break
                    self.events.append(event)
                if event['type']=='answer': answer=event['text']
                if event['type']=='done': finished=True
            except queue.Empty:
                if not process.is_alive(): break
            if time.monotonic()-started>300:
                self.cancel('Time budget reached')
                break
        process.join(timeout=1)
        with self.lock:
            if process is not self.process:
                q.close()
                job=self.jobs.pop(process.pid,None)
                if job is not None: job.Close()
                return
            if not finished and not any(e.get('type')=='done' for e in self.events):
                self.events.extend([{'type':'error','message':'Worker stopped before completion; partial artifacts are not completed findings.'}, {'type':'done','status':'failed'}])
            if answer and finished and any(e.get('status') in ('complete','partial') for e in self.events) and not any(e.get('status')=='cancelled' for e in self.events):
                notebooks=[e['artifact']['artifact_id'] for e in self.events if e.get('type')=='notebook']
                context_answer=answer
                if notebooks:context_answer+='\nPrevious investigation notebook artifact_id: '+notebooks[-1]+'. Its E IDs belong to that investigation; read the original evidence again before citing it in a new answer.'
                self.history.extend([{'role':'user','content':question},{'role':'assistant','content':context_answer}])
                self.history=self.history[-12:]
        q.close()
        job=self.jobs.pop(process.pid,None)
        if job is not None: job.Close()

    def cancel(self, reason='Cancelled by user'):
        with self.lock:
            process=self.process
            if process and process.is_alive():
                stop_process(process,self.jobs.get(process.pid))
                event={'type':'done','status':'cancelled','message':reason}
                self.events.append(event)
                with self.log.open('a',encoding='utf-8') as f: f.write(json.dumps(event)+'\n')


def make_server(app,port=8765):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def send(self,status,value,html=False):
            body=value.encode('utf-8') if html else json.dumps(value,ensure_ascii=False,default=str).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type','text/html; charset=utf-8' if html else 'application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'nonce-"+app.token+"'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def allowed(self, post=False):
            origin=f'http://127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host')!=origin[7:]: return False
            if self.headers.get('Origin') not in (None,origin): return False
            if post and (self.headers.get('X-IFs-Token')!=app.token or self.headers.get('Content-Type')!='application/json'): return False
            if self.path.startswith('/api/') and self.headers.get('X-IFs-Token')!=app.token: return False
            return True

        def do_GET(self):
            if not self.allowed(): return self.send(403,{'error':'Local origin/token required'})
            if self.path=='/':
                page=(Path(__file__).parent/'static/index.html').read_text(encoding='utf-8').replace('__TOKEN__',app.token)
                return self.send(200,page,True)
            if self.path=='/api/status': return self.send(200,app.status())
            if self.path=='/api/events':
                with app.lock: result={'events':list(app.events),'job':app.job}
                return self.send(200,result)
            return self.send(404,{'error':'Not found'})

        def do_POST(self):
            if not self.allowed(True): return self.send(403,{'error':'Local origin/token required'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=60000: raise ValueError('Request too large or empty')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict): raise ValueError('Expected a JSON object')
                if self.path=='/api/models': result=app.models(data)
                elif self.path=='/api/settings': result=app.save(data)
                elif self.path=='/api/chat': result=app.start(data.get('question'))
                elif self.path=='/api/refresh': result=app.refresh(data.get('kind'))
                elif self.path=='/api/cancel': app.cancel(); result={'cancelled':True}
                elif self.path=='/api/clear':
                    with app.lock:
                        if app.process and app.process.is_alive(): raise ValueError('Finish or cancel the active investigation first')
                        app.history=[]; app.events=[]; result={'cleared':True}
                elif self.path=='/api/artifact':
                    result=ToolService(app.settings['config'],app.artifacts).call('artifact_read',data)
                else: return self.send(404,{'error':'Not found'})
                self.send(200,result)
            except Exception as exc:
                message=str(exc)[:1500]
                if app.key: message=message.replace(app.key,'[REDACTED]')
                self.send(400,{'error':message})
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)
