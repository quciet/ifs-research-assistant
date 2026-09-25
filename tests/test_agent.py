"""Transport and trust-boundary tests; provider responses here are simulations, not model evaluations."""
import asyncio
import copy
import json
from pathlib import Path
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
import httpx
import test_investigation
from ifs_agent.tools import ToolService
from ifs_agent.provider import Provider, ProviderError, validate_settings
from ifs_agent.agent import run_loop
from ifs_agent.webapp import Application, make_server
from ifs_agent.sources import connect


def spawn_sleeping_child(channel):
    import subprocess
    import time
    child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
    channel.put(child.pid)
    time.sleep(60)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_investigation.InvestigationTests('test_unknown_version_still_explains_code_and_numbers')
        self.fixture.setUp(); self.root=self.fixture.root
        self.service=ToolService(self.fixture.config,self.root/'agent-artifacts')
    def tearDown(self): self.fixture.tearDown()

    def test_tool_schema_blocks_extra_paths_and_unknown_tools(self):
        for name,args in [('shell',{}),('code_search',{'query':'GDP','path':'C:/'}),('artifact_read',{'artifact_id':'../registry.json'}),('equality',{'dataset':'test','x':'X','y':'Y','atol':float('nan'),'rtol':0,'first_year':2022,'last_year':2024})]:
            with self.assertRaises(Exception): self.service.call(name,args)

    def test_status_and_code_have_citations(self):
        status=self.service.call('source_status',{})
        self.assertEqual(status['datasets'],['test'])
        source=self.service.call('code_read',{'path':'Balance.Forecast.vb','start':1,'end':3})
        self.assertIn('GDP = X + Y',source['text']); self.assertIn('snapshot',source['citation'])

    def test_source_index_change_rejected(self):
        (self.root/'sources/Balance.Forecast.vb').write_text('GDP = X - Y')
        self.fixture.research.code.index(self.root/'sources')
        self.assertNotEqual(self.service.call('source_status',{})['code']['snapshot'],self.fixture.research.code.current())
        old=self.service.call('code_read',{'path':'Balance.Forecast.vb','start':1,'end':3})
        self.assertIn('GDP = X + Y',old['text']);self.assertFalse(old['local_source_matches_snapshot'])

    def test_artifact_pagination_and_invalid_identity(self):
        artifact=self.service.publish('a'*13000)
        self.assertTrue(artifact['truncated'])
        result=self.service.call('artifact_read',{'artifact_id':artifact['artifact_id'],'offset':12000})
        self.assertEqual(result['text'],'a'*1000); self.assertIsNone(result['next_offset'])
        with self.assertRaises(ValueError): self.service.call('artifact_read',{'artifact_id':'../../secret'})

    def test_standard_analysis_uses_reproducible_core(self):
        result=self.service.call('equality',{'dataset':'test','x':'X','y':'Y','first_year':2022,'last_year':2024,'atol':0,'rtol':0})
        # Large summaries are paged rather than silently truncated.
        if 'artifact_id' in result: result=json.loads((self.service.root/(result['artifact_id']+'.txt')).read_text())
        self.assertIn('analysis.py',result['files'])
        evidence=json.loads((Path(result['folder'])/'evidence.json').read_text())
        self.assertTrue(evidence)
        self.assertTrue((Path(result['folder'])/'results.csv').is_file())

    def hypothesis(self):
        spec=copy.deepcopy(self.fixture.spec)
        for key in ('schema_version','review_status','source_snapshot'): spec.pop(key)
        for span in spec['code_evidence']:
            span.pop('file_sha256');span.pop('text_sha256')
        return spec

    def test_model_hypothesis_cannot_assert_provenance(self):
        spec=self.hypothesis();spec['version_evidence']='C:/secret'
        with self.assertRaisesRegex(ValueError,'provenance'):self.service.call('investigate',{'spec_json':json.dumps(spec)})

    def test_model_hypothesis_retains_unknown_conditions(self):
        result=self.service.call('investigate',{'spec_json':json.dumps(self.hypothesis())})
        if 'artifact_id' in result: result=json.loads((self.service.root/(result['artifact_id']+'.txt')).read_text())
        evidence=json.loads((Path(result['folder'])/'evidence.json').read_text())
        self.assertEqual(evidence['outcome'],'insufficient_evidence')
        self.assertTrue(all(p['status']=='unknown' for p in evidence['preconditions']))
        self.assertTrue(result['model_hypothesis_not_human_review'])

    def test_unknown_installation_gets_code_only(self):
        project=self.root/'assistant';(project/'resources').mkdir(parents=True)
        original=Path(__file__).resolve().parents[1]
        for name in ('pilot.json','research.json','countries-872.json','result-profiles.json'):
            (project/'resources'/name).write_bytes((original/'resources'/name).read_bytes())
        source=self.root/'installation/Code.Ifs-Translation/src/IFs.Core';source.mkdir(parents=True)
        (source/'X.vb').write_text('Public Sub X()\nGDP = 1\nEnd Sub')
        config=connect(project,source.parents[2])
        status=ToolService(config,project/'workspace/artifacts').call('source_status',{})
        self.assertFalse(status['numerical_access']);self.assertEqual(status['code_files'],1)
        self.assertEqual(list(source.iterdir()),[source/'X.vb'])
        # A reviewed byte fingerprint works even when the old pilot paths do not exist.
        from ifs_analysis.registry import fingerprint
        runfiles=source.parents[2]/'RUNFILES';runfiles.mkdir()
        relocated=runfiles/'Relocated.run.db';relocated.write_bytes(self.fixture.fixture.db.read_bytes())
        (project/'resources/result-profiles.json').write_text(json.dumps({'profiles':{fingerprint(relocated)['sha256']:{'payload_encoding':'standard','generating_version':None}}}))
        config=connect(project,source.parents[2])
        status=ToolService(config,project/'workspace/artifacts').call('source_status',{})
        self.assertEqual(status['datasets'],['Relocated'])

    def test_provider_loop_both_wire_protocols(self):
        for protocol in ('responses','chat_completions'):
            requests=[]
            class Mock(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_POST(self):
                    body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    requests.append(body)
                    if len(requests)==1:
                        if protocol=='responses': data={'status':'completed','output':[{'type':'reasoning','id':'r1','summary':[]},{'type':'function_call','call_id':'c1','name':'code_read','arguments':json.dumps({'path':'Balance.Forecast.vb','start':1,'end':3})}]}
                        else:data={'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[{'id':'c1','type':'function','function':{'name':'code_read','arguments':json.dumps({'path':'Balance.Forecast.vb','start':1,'end':3})}}]}}]}
                    elif protocol=='responses':data={'status':'completed','output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':json.dumps({'status':'answered','answer':'Fixture answer based on returned code [E0001].','unresolved':[]})}]}]}
                    else:data={'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps({'status':'answered','answer':'Fixture answer based on returned code [E0001].','unresolved':[]})}}]}
                    body=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            server=ThreadingHTTPServer(('127.0.0.1',0),Mock);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                settings={'protocol':protocol,'endpoint':f'http://127.0.0.1:{server.server_port}/v1','model':'simulated','api_key':''}
                events=[];text=run_loop(settings,self.service,'Explain GDP',emit=events.append)
                self.assertIn('Fixture answer',text);self.assertEqual(len(requests),3)
                items=requests[1]['input' if protocol=='responses' else 'messages']
                self.assertIn('GDP = X + Y',json.dumps(items))
                self.assertTrue(all(x.get('role') in ('user','system') for x in items)) # Fresh completed research turn, no orphan tool IDs.
                self.assertTrue(any(x['type']=='tool_result' for x in events))
            finally:server.shutdown();server.server_close();thread.join()

    def test_loop_tool_error_is_recoverable_and_budget_bounded(self):
        class Simulated:
            count=0
            def request(self,*args):
                self.count+=1
                if self.count==1:return [],[{'id':'c1','name':'shell','arguments':'{}'}],''
                return [],[],'Unsupported action was not executed.'
            def tool_output(self,call,result):
                assert not result['executed_successfully']
                return {'role':'tool','content':json.dumps(result)}
        events=[];run_loop({},self.service,'x',provider=Simulated(),emit=events.append)
        self.assertTrue(any(e['type']=='answer' for e in events))
        self.assertIn('Partial investigation:',run_loop({},self.service,'x',provider=Simulated(),max_steps=1))

    def test_context_budget_stops_before_provider_call(self):
        with self.assertRaisesRegex(ValueError,'Context budget'):
            run_loop({},self.service,'x'*150000,provider=object())

    def test_endpoint_validation(self):
        for endpoint in ('http://example.com/v1','https://key@example.com/v1','https://example.com/v1?key=secret','file:///x'):
            with self.assertRaises(ValueError):validate_settings({'model':'x','endpoint':endpoint})
        self.assertEqual(validate_settings({'model':'x','endpoint':'http://localhost:11434/v1'})['api_key'],'')

    def test_provider_errors_do_not_echo_secrets(self):
        p=Provider({'model':'x','endpoint':'https://example.com/v1','api_key':'secret-test'})
        with patch('httpx.Client',side_effect=RuntimeError('secret-test')):
            with self.assertRaises(ProviderError) as caught:p.request([],[],'')
        self.assertNotIn('secret-test',str(caught.exception))

    def test_http_origin_token_and_settings_secret_storage(self):
        app=Application(self.root);app.settings['config']=str(self.fixture.config)
        server=make_server(app,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            with httpx.Client(trust_env=False) as client:
                self.assertEqual(client.get(url+'/').status_code,200)
                self.assertEqual(client.get(url+'/api/status').status_code,403)
                headers={'X-IFs-Token':app.token,'Content-Type':'application/json'}
                data={'endpoint':'http://127.0.0.1:11434/v1','protocol':'chat_completions','model':'test','api_key':'secret-test'}
                self.assertEqual(client.post(url+'/api/settings',json=data,headers={**headers,'Origin':'https://evil.test'}).status_code,403)
                response=client.post(url+'/api/settings',json=data,headers=headers)
                self.assertEqual(response.status_code,200,response.text)
                self.assertNotIn('secret-test',response.text);self.assertNotIn('secret-test',app.path.read_text())
                self.assertTrue(response.json()['key_present'])
                data.update(api_key='',endpoint='https://example.com/v1');app.save(data)
                self.assertFalse(app.key)
                self.assertEqual(client.get(url+'/',headers={'Host':'evil.test'}).status_code,403)
        finally:server.shutdown();server.server_close();thread.join()

    @unittest.skipUnless(sys.platform=='win32','Windows worker-tree guarantee')
    def test_cancel_terminates_decoder_descendant(self):
        import multiprocessing as mp
        import win32api, win32con, win32event
        from ifs_agent.processes import own_process,stop_process
        context=mp.get_context('spawn');channel=context.Queue()
        process=context.Process(target=spawn_sleeping_child,args=(channel,));process.start()
        job=own_process(process);handle=None
        try:
            pid=channel.get(timeout=15)
            handle=win32api.OpenProcess(win32con.SYNCHRONIZE,False,pid)
            stop_process(process,job)
            self.assertEqual(win32event.WaitForSingleObject(handle,5000),win32event.WAIT_OBJECT_0)
        finally:
            if process.is_alive():stop_process(process,job)
            if handle:handle.Close()
            if job:job.Close()
            channel.close()

    def test_worker_cancel_stops_active_process_and_keeps_key_out_of_log(self):
        import time
        app=Application(self.root);app.settings.update(config=str(self.fixture.config),model='simulated',endpoint='http://127.0.0.1:1/v1')
        app.key='secret-test-value'
        app.start('Cancellation fixture')
        with self.assertRaisesRegex(ValueError,'already running'):app.start('second')
        app.cancel()
        self.assertFalse(app.process.is_alive())
        self.assertNotIn(app.key,app.log.read_text())
        self.assertTrue(any(e.get('status')=='cancelled' for e in app.events))

    def test_worker_http_round_trip_and_log(self):
        import time
        class Mock(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                body=json.dumps({'status':'completed','output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':json.dumps({'status':'partial','answer':'Simulated worker completed.','unresolved':['No evidence requested by fixture']})}]}]}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Mock);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        app=Application(self.root);app.settings.update(config=str(self.fixture.config),model='simulated',endpoint=f'http://127.0.0.1:{server.server_port}/v1')
        app.key='fake-key-for-test'
        try:
            app.start('A simulated worker test')
            deadline=time.monotonic()+20
            while not any(e.get('type')=='done' for e in app.events) and time.monotonic()<deadline: time.sleep(.1)
            self.assertTrue(any(e.get('status')=='partial' for e in app.events),app.events)
            app.process.join(timeout=5)
            self.assertNotIn(app.key,app.log.read_text())
            self.assertIn('Simulated worker completed.',app.log.read_text())
        finally:app.cancel();server.shutdown();server.server_close();thread.join()

    def test_mcp_official_client_interoperability(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        async def check():
            params=StdioServerParameters(command=sys.executable,args=['-m','ifs_agent','--project',str(self.root),'mcp','--config',str(self.fixture.config)])
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as client:
                    await client.initialize()
                    listing=await client.list_tools()
                    self.assertIn('code_read',[x.name for x in listing.tools])
                    result=await client.call_tool('code_read',{'path':'Balance.Forecast.vb','start':1,'end':3})
                    self.assertFalse(result.isError)
                    self.assertIn('GDP = X + Y',result.content[0].text)
                    bad=await client.call_tool('artifact_read',{'artifact_id':'../private'})
                    self.assertTrue(bad.isError)
        asyncio.run(check())


if __name__=='__main__':unittest.main()
