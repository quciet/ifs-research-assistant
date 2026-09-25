import json
import unittest
from ifs_agent.context import EvidenceContext,size
from ifs_agent.provider import Provider
from ifs_agent.agent import run_loop

class Store:
    def __init__(self):self.saved={}
    def publish(self,value):
        key=str(len(self.saved));text=json.dumps(value);self.saved[key]=value
        return {'artifact_id':key,'characters':len(text)}
    def call(self,name,args):return {'text':'evidence '*2000,'citation':{'path':'model.vb','snapshot':'pinned','line':42},'complete':False}

class ContextTests(unittest.TestCase):
    def provider(self,protocol):return Provider({'protocol':protocol,'endpoint':'http://localhost:1','model':'fixture'})
    def test_archive_preserves_exact_results_and_tool_ids_all_protocols(self):
        for protocol in ('responses','chat_completions','anthropic'):
            store=Store();p=self.provider(protocol);initial=[{'role':'user','content':'question'}];messages=list(initial)
            ctx=EvidenceContext(store,p,initial,lambda e:None,budget=8000)
            value=store.call('',{})
            for i in range(3):ctx.add(messages,{'id':str(i),'name':'code_read'},value,{'start':1,'end':200})
            fitted=ctx.fit(messages)
            self.assertLessEqual(size(fitted),8000)
            self.assertEqual(store.saved['0'],value)
            joined=json.dumps(fitted)
            self.assertIn('artifact_id',joined);self.assertIn('pinned',joined)
            self.assertEqual(len(fitted),4) # No tool-message pairs removed.
            for i in range(3):
                message=fitted[i+1]
                call_id=message.get('call_id') or message.get('tool_call_id') or message['content'][0]['tool_use_id']
                self.assertEqual(call_id,str(i))

    def test_reasoning_overflow_creates_complete_turn_checkpoint(self):
        store=Store();p=self.provider('chat_completions');initial=[{'role':'user','content':'original question'}]
        messages=[*initial,{'role':'assistant','content':None,'reasoning_content':'x'*20000,'tool_calls':[]}]
        ctx=EvidenceContext(store,p,initial,lambda e:None,budget=6000)
        ctx.add(messages,{'id':'1','name':'code_read'},store.call('',{}),{})
        fitted=ctx.fit(messages)
        self.assertEqual(fitted[0],initial[0]);self.assertEqual(fitted[-1]['role'],'user')
        self.assertIn('evidence ledger',fitted[-1]['content']);self.assertLess(size(fitted),6000)
        self.assertTrue(all(r['index'] is None for r in ctx.records))
        ctx.add(fitted,{'id':'2','name':'code_read'},store.call('',{}),{})
        self.assertLessEqual(size(ctx.fit(fitted)),6000)

    def test_long_tool_investigation_reaches_final_answer_under_budget(self):
        store=Store();formatter=self.provider('chat_completions');events=[]
        class Model:
            steps=0
            def request(self,conversation,tools,prompt):
                self.steps+=1
                assert size(conversation)<35000
                if not tools:return [],[],json.dumps({'status':'partial','answer':'Bounded supported answer [E0001].','unresolved':['Further checks needed']})
                call={'id':str(self.steps),'name':'code_read','arguments':'{}'}
                return [{'role':'assistant','content':None,'tool_calls':[{'id':call['id'],'type':'function','function':{'name':'code_read','arguments':'{}'}}]}],[call],''
            def tool_output(self,call,value):return formatter.tool_output(call,value)
        answer=run_loop({},store,'Investigate yield and poverty',provider=Model(),max_steps=12,context_budget=35000,emit=events.append)
        self.assertIn('Bounded supported answer',answer)
        self.assertTrue(store.saved);self.assertTrue(any(e['type']=='notebook' for e in events))

class ToolBudgetTests(unittest.TestCase):
    def test_batches_crossing_limit_pair_every_call_and_summarize(self):
        for protocol in ('responses','chat_completions','anthropic'):
            for batches,expected in (([7,7,7,7,1,4],32),([9],8),([8,8,8,8],32)):
                with self.subTest(protocol=protocol,batches=batches):
                    store=Store();executed=[];results=[];events=[]
                    store.call=lambda name,args: executed.append(args) or {'value':42}
                    formatter=Provider({'protocol':protocol,'endpoint':'http://localhost:1','model':'fixture'})
                    class Model:
                        index=0
                        def request(self,conversation,tools,prompt):
                            if not tools:
                                assert all(m['role']=='user' for m in conversation)
                                return [],[],json.dumps({'status':'partial','answer':'Partial findings [E0001]; further checks remain unresolved.','unresolved':['Further checks']})
                            count=batches[self.index];self.index+=1
                            calls=[{'id':f'{self.index}-{i}','name':'code_read','arguments':json.dumps({'i':i,'batch':self.index})} for i in range(count)]
                            return [],calls,''
                        def tool_output(self,call,result):
                            message=formatter.tool_output(call,result)
                            results.append((call,result,message));return message
                    answer=run_loop({},store,'question',provider=Model(),emit=events.append)
                    self.assertEqual(len(executed),expected)
                    self.assertEqual(sum(bool(e.get('result',{}).get('not_executed')) for e in events if e['type']=='tool_result'),sum(batches)-expected)
                    self.assertIn('Partial findings',answer)
                    self.assertFalse(any(e['type']=='error' for e in events))

    def test_saved_deepseek_markup_is_not_accepted_as_answer(self):
        from ifs_agent.agent import contains_tool_markup
        markup='<\uff5c\uff5cDSML\uff5c\uff5c calls>\n<\uff5c\uff5cDSML\uff5c\uff5c invoke name="code_read">'
        self.assertTrue(contains_tool_markup(markup))
        self.assertTrue(contains_tool_markup('< | | DSML | | calls>'.replace('| |','||')))
        self.assertFalse(contains_tool_markup('The code_read tool provided evidence; DSML is a format.'))
        executed=[];events=[];store=Store()
        store.call=lambda *args:executed.append(args)
        class Model:
            def request(self,*args):return [],[],markup
        answer=run_loop({},store,'question',provider=Model(),max_steps=1,emit=events.append)
        self.assertIn('Partial investigation:',answer)
        self.assertNotIn('DSML',answer)
        self.assertEqual(executed,[])
        self.assertTrue(all(e['outcome']=='partial' for e in events if e['type']=='answer'))

    def test_model_ignoring_final_request_does_not_execute_more_tools(self):
        store=Store();executed=[]
        store.call=lambda *args:executed.append(args)
        class Model:
            def request(self,*args):return [],[{'id':'extra','name':'code_read','arguments':'{}'}],''
        answer=run_loop({},store,'question',provider=Model(),max_steps=1)
        self.assertIn('Partial investigation:',answer)
        self.assertEqual(executed,[])

if __name__=='__main__':unittest.main()
