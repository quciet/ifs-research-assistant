import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from ifs_research.structure import parse_vb,StructureStore
from ifs_research.service import Research
from ifs_research.retrieval import RetrievalStore
from ifs_agent.notebook import Notebook
from ifs_agent.provider import normalize_usage
from ifs_agent.agent import run_loop


class MemoryArtifacts:
    def __init__(self):self.saved={};self.executed=0
    def publish(self,value):
        key=f'{len(self.saved):032x}';self.saved[key]=value
        return {'artifact_id':key,'characters':len(json.dumps(value))}
    def call(self,name,args):
        self.executed+=1
        return {'text':'Production = Yield * Land','citation':{'snapshot':'fixed','path':'A.vb','start':2,'end':2}}


class StructuralTests(unittest.TestCase):
    def test_multiline_assignment_indices_branch_and_compound(self):
        source='''Public Sub Forecast()
If Year = 1 Then
  Production(r, sector) = Yield(r) * _
      Land(r, sector)
Else
  Production(r, sector) += Stock(r)
End If
End Sub'''
        parsed=parse_vb(source,'A.Forecast.vb')
        assigns=[x for x in parsed['records'] if x['kind']=='assignment']
        self.assertEqual(len(assigns),2)
        self.assertEqual(assigns[0]['target'],'Production(r, sector)')
        self.assertEqual(assigns[0]['end'],4)
        self.assertIn('yield',assigns[0]['inputs'])
        self.assertNotIn('production',assigns[0]['inputs'])
        self.assertIn('production',assigns[1]['inputs'])
        self.assertEqual(assigns[1]['conditions'][0]['branches'],['If Year = 1 Then','Else'])
        self.assertEqual(assigns[0]['index_references'],['r','sector'])

    def test_comments_strings_inline_if_declarations_and_unresolved_calls(self):
        parsed=parse_vb('''Dim A(,), B As Single
Public Sub F()
' Fake = Wrong
If A = B Then A = 2
X = F(A) + B ' comment Z
Msg = "Secret = Y"
End Sub''','A.vb')
        self.assertTrue(any('Single-line If' in x['reason'] for x in parsed['warnings']))
        self.assertEqual([x['symbol'] for x in parsed['records'] if x['kind']=='declaration'],['a','b'])
        assigns=[x for x in parsed['records'] if x['kind']=='assignment']
        self.assertEqual([x['symbol'] for x in assigns],['x','msg'])
        self.assertEqual(assigns[-1]['inputs'],[])
        self.assertTrue(any(x['kind']=='call_candidate' and x['symbol']=='f' for x in parsed['records']))

    def test_scalar_type_suffix_and_declaration_initializer(self):
        parsed=parse_vb('Public Sub F()\nDim A As Single = B + 1\nCount% = Count% + 1\nEnd Sub','A.vb')
        rows=[x for x in parsed['records'] if x['kind']=='assignment']
        self.assertEqual(rows[0]['symbol'],'a');self.assertEqual(rows[0]['inputs'],['b'])
        self.assertTrue(rows[0]['declaration_initializer'])
        self.assertEqual(rows[1]['target'],'Count%');self.assertEqual(rows[1]['symbol'],'count')


class IndexTests(unittest.TestCase):
    def setUp(self):
        base=Path(__file__).resolve().parents[1]/'workspace/tests';base.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base);self.root=Path(self.tmp.name)
        (self.root/'source').mkdir()
        (self.root/'source/A.Forecast.vb').write_text('Public Sub F()\nProduction = Yield * Land\nEnd Sub',encoding='utf-8')
        (self.root/'source/B.vb').write_text('Public Sub G()\nPoverty = Income\nEnd Sub',encoding='utf-8')
        (self.root/'registry.json').write_text('{"datasets":{}}',encoding='utf-8')
        cfg=self.root/'research.json';cfg.write_text(json.dumps({'workspace':'work','code_root':'source','results_registry':'registry.json'}),encoding='utf-8')
        self.r=Research(cfg);self.r.code.index(self.root/'source')
    def tearDown(self):self.tmp.cleanup()
    def test_read_context_retains_initial_year_branch(self):
        path=self.root/'source/A.Forecast.vb'
        path.write_text('Public Sub F()\nIf IY = 1 Then\nWage = Min(0.5 * OtherWage, Wage)\nElse\nWage = SavedWage\nEnd If\nEnd Sub',encoding='utf-8')
        self.r.code.index(self.root/'source')
        scopes=StructureStore(self.r.code).scopes('A.Forecast.vb',1,7)
        self.assertEqual(scopes['distinct_contexts'],2)
        self.assertEqual(scopes['contexts'][0]['conditions'][0]['text'],'If IY = 1 Then')
        self.assertEqual(scopes['contexts'][1]['conditions'][0]['text'],'Else')
        self.assertIn('Initialization',scopes['notice'])

    def test_incremental_structure_keeps_prior_snapshot_and_sources_unchanged(self):
        original=(self.root/'source/A.Forecast.vb').read_bytes()
        store=StructureStore(self.r.code);first=store.build();sid=first['snapshot']
        self.assertEqual(first['parsed'],2)
        self.assertEqual(store.lookup('Yield',kind='uses')['hits'][0]['symbol'],'production')
        (self.root/'source/B.vb').write_text('Public Sub G()\nPoverty = Income + Tax\nEnd Sub',encoding='utf-8')
        self.r.code.index(self.root/'source');second=store.build()
        self.assertEqual(second['parsed'],1);self.assertEqual(second['reused'],1)
        self.assertEqual(store.lookup('poverty',kind='assignment',snapshot=sid)['hits'][0]['expression'],'Income')
        self.assertEqual((self.root/'source/A.Forecast.vb').read_bytes(),original)
    def test_semantic_cache_model_change_and_offline_fallback(self):
        class Encoder:
            identity='test-model-1';calls=0
            def embed(self,texts,query=False):
                self.calls+=len(texts)
                return np.array([[1,0] if ('Yield' in text or 'crop productivity' in text) else [0,1] for text in texts],dtype=np.float32)
        enc=Encoder();store=RetrievalStore(self.r)
        first=store.prepare(encoder=enc);self.assertGreater(first['embedded'],0)
        second=store.prepare(encoder=enc);self.assertEqual(second['embedded'],0)
        result=store.search('crop productivity');self.assertEqual(result['semantic_status'],'local embeddings active')
        self.assertIn('Production',result['hits'][0]['text'])
        oldcorpus=result['corpus']
        (self.root/'source/B.vb').write_text('Public Sub G()\nPoverty = Income + Tax\nEnd Sub',encoding='utf-8')
        self.r.code.index(self.root/'source')
        result=store.search('Poverty');self.assertIn('unavailable',result['semantic_status'])
        self.assertEqual(store.search('crop productivity',corpus=oldcorpus)['semantic_status'],'local embeddings active')
        enc.identity='test-model-2';self.assertIn('unavailable',store.search('Yield')['semantic_status'])
        self.assertGreater(store.prepare(encoder=enc)['embedded'],0)

    def test_wiki_snapshot_and_approval_survive_refresh(self):
        from test_research import page
        from ifs_agent.tools import PinnedWiki
        original=page();original['selection']='latest_fallback';original['approval']['status']='unknown'
        original['approval']['reason']='Approval unavailable'
        self.r.wiki.put(original)
        pinned=PinnedWiki(self.r.wiki)
        self.r.wiki.put(page(rev=9))
        item=pinned.search('IGCF')[0]
        self.assertEqual(item['revision'],4);self.assertEqual(item['selection'],'latest_fallback')
        self.assertEqual(item['approval']['status'],'unknown')
        self.assertFalse(item['is_current_local_selection'])
        self.r.wiki=pinned
        retrieved=RetrievalStore(self.r).search('IGCF',semantic=False)
        wiki=[x for x in retrieved['hits'] if x['kind']=='wiki']
        self.assertEqual(wiki[0]['revision'],4);self.assertEqual(wiki[0]['selection'],'latest_fallback')


class WorkflowTests(unittest.TestCase):
    def test_provider_token_accounting_preserves_missing_and_cache_subsets(self):
        self.assertIsNone(normalize_usage(None,'responses'))
        result=normalize_usage({'input_tokens':10,'output_tokens':3,'cache_read_input_tokens':20,'cache_creation_input_tokens':5},'anthropic')
        self.assertEqual(result['input_tokens'],35);self.assertEqual(result['cached_input_tokens'],20)
        result=normalize_usage({'prompt_tokens':100,'completion_tokens':20,'completion_tokens_details':{'reasoning_tokens':8}},'chat_completions')
        self.assertEqual(result['output_tokens'],20);self.assertEqual(result['reasoning_tokens'],8)
        self.assertIsNone(result['cached_input_tokens'])
    def test_notes_reject_unknown_evidence_and_writer_rejects_false_citations(self):
        book=Notebook(MemoryArtifacts(),'question');book.add('code_read',{}, {'text':'source'})
        with self.assertRaises(ValueError):book.update([{'text':'claim','evidence_ids':['E9999']}],[])
        book.update([{'text':'claim','evidence_ids':['E0001']}],['unknown net effect'])
        self.assertEqual(book.notes[0]['status'],'model_interpretation_not_independently_verified')
        for answer in ('Claim [E9999]','Claim without citation'):
            with self.assertRaises(ValueError):book.validate_answer({'status':'answered','answer':answer,'unresolved':[]})
    def test_grouped_citations_are_normalized_but_unknown_ids_rejected(self):
        book=Notebook(MemoryArtifacts(),'question')
        book.add('code_read',{}, {'text':'a'});book.add('code_read',{}, {'text':'b'})
        value,refs=book.validate_answer({'status':'answered','answer':'Claim [E1, E0002].','unresolved':[]})
        self.assertEqual(value['answer'],'Claim [E0001] [E0002].');self.assertEqual(len(refs),2)
        with self.assertRaises(ValueError):book.validate_answer({'status':'answered','answer':'Claim [E1, E9999].','unresolved':[]})

    def test_cache_fresh_context_and_writer_repair(self):
        store=MemoryArtifacts();events=[]
        class Model:
            research=0;writer=0;last_usage=None
            def request(self,messages,tools,prompt):
                self.last_usage={'input_tokens':20,'output_tokens':5}
                self.assertion=all(m.get('role')=='user' for m in messages)
                if tools:
                    self.research+=1
                    if self.research==3:return [],[],'Ready'
                    return [],[{'id':str(self.research),'name':'code_read','arguments':'{}'}],''
                self.writer+=1
                if self.writer==1:return [],[],'<｜｜DSML｜｜ calls>'
                return [],[],json.dumps({'status':'answered','answer':'Production depends on yield and land [E0001].','unresolved':[]})
        model=Model();answer=run_loop({},store,'question',provider=model,emit=events.append)
        self.assertIn('depends on yield',answer);self.assertNotIn('DSML',answer)
        self.assertEqual(store.executed,1);self.assertTrue(model.assertion)
        summary=events[-1]['summary']
        self.assertEqual(summary['reused_tool_calls'],1)
        self.assertEqual(summary['stages']['writer_correction']['requests'],1)
        self.assertEqual([e['outcome'] for e in events if e['type']=='answer'],['answered'])
    def test_writer_that_never_complies_is_partial_and_bounded(self):
        store=MemoryArtifacts();events=[]
        class Model:
            calls=0
            def request(self,*args):self.calls+=1;return [],[],'<｜｜DSML｜｜ calls>'
        model=Model();answer=run_loop({},store,'question',provider=model,emit=events.append)
        self.assertEqual(model.calls,3);self.assertEqual(store.executed,0)
        self.assertIn('Partial investigation',answer)
        self.assertEqual([e['outcome'] for e in events if e['type']=='answer'],['partial'])


if __name__=='__main__':unittest.main()
