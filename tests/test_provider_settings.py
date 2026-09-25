"""Provider catalog and native Claude protocol tests; no real API keys or billable calls."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx
from ifs_agent.catalog import PRESETS,list_models
from ifs_agent.provider import Provider,ProviderError
from ifs_agent.agent import run_loop
from ifs_agent.webapp import Application

class ProviderSettingsTests(unittest.TestCase):
    def transport(self,handler):
        cls=httpx.Client
        return patch('httpx.Client',side_effect=lambda **kw: cls(transport=httpx.MockTransport(handler),**kw))

    def test_presets_and_exact_live_ids(self):
        for preset in PRESETS.values():
            def handler(request):
                self.assertEqual(str(request.url),preset['endpoint']+'/models')
                if preset['protocol']=='anthropic':
                    self.assertEqual(request.headers['x-api-key'],'fake-key')
                    self.assertEqual(request.headers['anthropic-version'],'2023-06-01')
                    self.assertNotIn('authorization',request.headers)
                else:self.assertEqual(request.headers['authorization'],'Bearer fake-key')
                return httpx.Response(200,json={'data':[{'id':'brand-new-model-id','display_name':'New model'}]})
            with self.transport(handler): result=list_models({**preset,'api_key':'fake-key'})
            self.assertEqual(result['models'],[{'id':'brand-new-model-id','label':'New model'}])

    def test_anthropic_pagination(self):
        requests=[]
        def handler(request):
            requests.append(request)
            if len(requests)==1:return httpx.Response(200,json={'data':[{'id':'first'}],'has_more':True,'last_id':'first'})
            self.assertEqual(request.url.params['after_id'],'first')
            return httpx.Response(200,json={'data':[{'id':'second'}],'has_more':False})
        with self.transport(handler): result=list_models({**PRESETS['claude'],'api_key':'fake'})
        self.assertEqual(len(result['models']),2)

    def test_pagination_does_not_follow_remote_links_or_loop(self):
        requests=[]
        def handler(request):
            requests.append(str(request.url))
            return httpx.Response(200,json={'data':[{'id':'same'}],'has_more':True,'last_id':'same','next':'https://evil.test/'})
        with self.transport(handler),self.assertRaisesRegex(ProviderError,'repeated'):
            list_models({**PRESETS['claude'],'api_key':'fake'})
        self.assertTrue(all(u.startswith(PRESETS['claude']['endpoint']) for u in requests))

    def test_http_errors_and_redirect_never_expose_key_or_response_body(self):
        for status in (301,401,403,429,500):
            calls=[]
            def handler(request):
                calls.append(request)
                return httpx.Response(status,headers={'Location':'https://evil.test/'},text='secret-fake-key')
            with self.transport(handler),self.assertRaises(ProviderError) as error:
                list_models({**PRESETS['openai'],'api_key':'secret-fake-key'})
            self.assertNotIn('secret-fake-key',str(error.exception));self.assertEqual(len(calls),1)

    def test_empty_malformed_and_oversized_lists(self):
        with self.transport(lambda r:httpx.Response(200,json={'data':[]})):
            self.assertEqual(list_models(PRESETS['deepseek'])['models'],[])
        for payload in ({'models':[]},{'data':[{'id':42}]}, {'data':[{'id':'x'*201}]}):
            with self.transport(lambda r:httpx.Response(200,json=payload)),self.assertRaises(ProviderError):list_models(PRESETS['openai'])
        with self.transport(lambda r:httpx.Response(200,content=b'x'*2_000_001)),self.assertRaises(ProviderError):list_models(PRESETS['openai'])

    def test_discovery_reuses_only_matching_connection_and_never_saves_key(self):
        root=Path(__file__).resolve().parents[1]/'workspace/tests';root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as folder:
            app=Application(folder);app.key='existing-key'
            with patch('ifs_agent.webapp.list_models',return_value={'models':[]}) as fetch:
                app.models({'endpoint':app.settings['endpoint'],'protocol':'responses','api_key':''})
                self.assertEqual(fetch.call_args.args[0]['api_key'],'existing-key')
                app.models({'endpoint':app.settings['endpoint'],'protocol':'anthropic','api_key':''})
                self.assertEqual(fetch.call_args.args[0]['api_key'],'')
                app.models({**PRESETS['deepseek'],'api_key':'new-unsaved-key'})
                self.assertEqual(fetch.call_args.args[0]['api_key'],'new-unsaved-key')
            self.assertEqual(app.key,'existing-key');self.assertFalse(app.path.exists())

    def test_claude_notebook_and_writer_protocol(self):
        requests=[]
        def handler(request):
            body=json.loads(request.content);requests.append(body)
            self.assertEqual(request.url.path,'/v1/messages')
            self.assertEqual(request.headers['x-api-key'],'fake')
            if len(requests)==1:
                self.assertIn('input_schema',body['tools'][0])
                return httpx.Response(200,json={'stop_reason':'tool_use','content':[{'type':'text','text':'Checking.'},{'type':'tool_use','id':'tool1','name':'source_status','input':{}}]})
            self.assertTrue(all(x['role']=='user' for x in body['messages']))
            self.assertIn('fixture evidence',json.dumps(body['messages']))
            if len(requests)==3:self.assertNotIn('tools',body)
            return httpx.Response(200,json={'stop_reason':'end_turn','content':[{'type':'text','text':json.dumps({'status':'answered','answer':'Simulated Claude answer [E0001].','unresolved':[]})}]})
        from test_efficiency import MemoryArtifacts
        class Service(MemoryArtifacts):
            def call(self,name,args):return {'source':'fixture evidence'}
        with self.transport(handler):
            result=run_loop({**PRESETS['claude'],'model':'test-claude','api_key':'fake'},Service(),'Explain the code')
        self.assertIn('Simulated Claude answer',result)
        self.assertEqual(len(requests),3)

    def test_deepseek_writer_disables_thinking_only_on_official_endpoint(self):
        for endpoint in ('https://api.deepseek.com','https://example.com'):
            def handler(request):
                body=json.loads(request.content)
                self.assertEqual(body['tool_choice'],'none');self.assertNotIn('tools',body)
                if endpoint=='https://api.deepseek.com':
                    self.assertEqual(body['thinking'],{'type':'disabled'})
                    self.assertEqual(body['response_format'],{'type':'json_object'})
                else:self.assertNotIn('thinking',body)
                return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'{}'}}],
                    'usage':{'prompt_tokens':100,'completion_tokens':20,'prompt_cache_hit_tokens':30}})
            model=Provider({'endpoint':endpoint,'protocol':'chat_completions','model':'fixture'})
            model.stage='writer'
            with self.transport(handler):model.request([],[],'Return JSON')
            self.assertEqual(model.last_usage['input_tokens'],100)
            self.assertEqual(model.last_usage['cached_input_tokens'],30)

    def test_blocked_network_explained_without_blame_or_secret(self):
        from ifs_agent.provider import transport_error
        inner=httpx.ConnectError('[WinError 10013] forbidden; fake-secret-key')
        outer=httpx.ConnectError('connection error');outer.__cause__=inner
        message=str(transport_error(outer,'Model discovery'))
        self.assertIn('execution environment',message)
        self.assertIn('not an API-key validation failure',message)
        self.assertNotIn('fake-secret-key',message)
        with patch('httpx.Client',side_effect=outer),self.assertRaisesRegex(ProviderError,'Windows 10013'):
            list_models({**PRESETS['deepseek'],'api_key':'fake-secret-key'})

    def test_claude_incomplete_turn_rejected(self):
        with self.transport(lambda r:httpx.Response(200,json={'stop_reason':'max_tokens','content':[]})):
            with self.assertRaisesRegex(ProviderError,'complete'):
                Provider({**PRESETS['claude'],'model':'test','api_key':'fake'}).request([],[],'prompt')

if __name__=='__main__':unittest.main()
