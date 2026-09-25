"""Deterministic fixtures for revision policy and local evidence navigation; no live HTTP."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from ifs_research.common import Config, ResearchError, database
from ifs_research.wiki_client import Transport, WikiClient, MissingPage, approval_from_html
from ifs_research.wiki_store import WikiStore
from ifs_research.code_store import CodeStore, assignment_lhs, clean_vb, routines
from ifs_research.extraction import extract_sections

ROOT = Path(__file__).resolve().parents[1]


def html(status='approved', revision=4, page_id=1):
    marker = {'approved':'approvedRevs-approved', 'absent':'approvedRevs-noapprovedrev'}.get(status, '')
    return '<script>RLCONF=' + json.dumps({'wgArticleId':page_id, 'wgRevisionId':revision, 'wgAction':'view'}) + ';</script><body class="' + marker + '"></body>'


class FakeTransport:
    index = 'https://example.test/index.php'
    def __init__(self, statuses=('approved','approved'), mismatch=False):
        self.statuses = iter(statuses); self.calls = []; self.mismatch = mismatch
    def get(self, url):
        state = next(self.statuses)
        if isinstance(state, Exception): raise state
        return html(state)
    def api_get(self, **p):
        self.calls.append(p)
        if p['action'] == 'parse':
            return {'parse':{'pageid':1, 'revid':999 if self.mismatch else p['oldid'], 'title':'Canonical', 'text':'<h2 id="a">Investment</h2><p>IGCF investment</p>', 'wikitext':'IGCF investment', 'links':[]}}
        if 'revids' in p:
            return {'query':{'pages':[{'pageid':1,'revisions':[{'revid':p['revids'],'timestamp':'2020-01-01T00:00:00Z'}]}]}}
        return {'query':{'pages':[{'pageid':1,'title':'Canonical','ns':0,'lastrevid':9}]}}


def page(title='A', pid=1, rev=4, links=()):
    return {'page_id':pid, 'title':title, 'requested_title':title, 'revision':rev, 'latest_revision_at_selection':9,
            'revision_timestamp':'2020-01-01T00:00:00Z', 'selection':'approved',
            'approval':{'status':'approved','revision':rev,'checked_at':'2026-01-01T00:00:00Z'},
            'fetched_at':'2026-01-01T00:00:00Z', 'url':f'https://example.test/?oldid={rev}',
            'content':{'text':'<h2 id="investment">Investment</h2><p>IGCF investment content</p>', 'wikitext':'IGCF',
                       'links':[{'ns':0,'title':t} for t in links]}}


class PolicyTests(unittest.TestCase):
    def test_approved_selects_older(self):
        t=FakeTransport(); p=WikiClient(t).fetch('Alias')
        self.assertEqual(p['revision'],4); self.assertEqual(p['latest_revision_at_selection'],9)
        self.assertEqual(p['selection'],'approved'); self.assertIn('oldid=4',p['url'])
        self.assertEqual(p['requested_title'],'Alias')
        self.assertEqual(next(x['oldid'] for x in t.calls if x['action']=='parse'),4)
    def test_latest_already_approved(self):
        t=FakeTransport()
        with patch.object(t,'get',return_value=html(revision=9)):
            p=WikiClient(t).fetch('A')
        self.assertEqual(p['revision'],9);self.assertEqual(p['selection'],'approved')
    def test_no_approval_latest(self):
        p=WikiClient(FakeTransport(('absent','absent'))).fetch('A')
        self.assertEqual(p['revision'],9); self.assertEqual(p['approval']['status'],'absent')
        self.assertEqual(p['selection'],'latest_fallback')
    def test_unverifiable_latest(self):
        for states in [('unknown','unknown'),(ResearchError('offline approval'),ResearchError('offline approval'))]:
            p=WikiClient(FakeTransport(states)).fetch('A')
            self.assertEqual(p['revision'],9); self.assertEqual(p['approval']['status'],'unknown')
            self.assertTrue(p['approval']['reason'])
    def test_marker_identity_and_action(self):
        self.assertEqual(approval_from_html(html(page_id=2),1)['status'],'unknown')
        self.assertEqual(approval_from_html(html().replace('"view"','"edit"'),1)['status'],'unknown')
        self.assertEqual(approval_from_html('<p>approvedRevs-approved RLCONF={};</p>',1)['status'],'unknown')
    def test_conflicting_approval_markers_are_unknown(self):
        value=html().replace('approvedRevs-approved','approvedRevs-approved approvedRevs-noapprovedrev')
        self.assertEqual(approval_from_html(value,1)['status'],'unknown')
    def test_revision_content_mismatch(self):
        with self.assertRaisesRegex(ResearchError,'does not match'):WikiClient(FakeTransport(mismatch=True)).fetch('A')
    def test_approval_race_retries(self):
        p=WikiClient(FakeTransport(('approved','absent','absent','absent'))).fetch('A')
        self.assertEqual(p['revision'],9); self.assertEqual(p['selection'],'latest_fallback')
    def test_approval_race_never_stores_mixed(self):
        with self.assertRaisesRegex(ResearchError,'changed'):WikiClient(FakeTransport(('approved','absent','approved','absent'))).fetch('A')
    def test_missing_and_namespace_rejected(self):
        for value in [{'missing':True},{'pageid':3,'ns':1,'title':'Talk:A','lastrevid':5}]:
            t=FakeTransport()
            with patch.object(t,'api_get',return_value={'query':{'pages':[value]}}):
                with self.assertRaises(MissingPage):WikiClient(t).fetch('A')


class Response(io.BytesIO):
    def geturl(self):return 'https://example.test/api.php'


class TransportTests(unittest.TestCase):
    def transport(self, opener):
        self.waits=[]
        return Transport('https://example.test/api.php',opener=opener,sleep=self.waits.append,clock=lambda:0)
    def test_retry_429_and_spacing(self):
        calls=[]
        def opener(req,timeout):
            calls.append(req)
            if len(calls)==1:raise HTTPError(req.full_url,429,'busy',{'Retry-After':'2'},None)
            return Response(b'{}')
        t=self.transport(opener)
        self.assertEqual(t.api_get(action='query'),{})
        self.assertEqual(len(calls),2); self.assertIn(2,self.waits); self.assertIn(1,self.waits)
    def test_retry_after_deferred(self):
        def opener(req,timeout):raise HTTPError(req.full_url,429,'busy',{'Retry-After':'120'},None)
        with self.assertRaisesRegex(ResearchError,'deferred'):self.transport(opener).get('https://example.test/api.php')
    def test_three_connection_attempts(self):
        calls=[]
        def opener(req,timeout):calls.append(1);raise OSError('disconnected')
        with self.assertRaises(ResearchError):self.transport(opener).get('https://example.test/api.php')
        self.assertEqual(len(calls),3)
    def test_json_errors_and_read_only(self):
        t=self.transport(lambda *a,**kw:Response(b'not json'))
        with self.assertRaisesRegex(ResearchError,'JSON'):t.api_get(action='query')
        with self.assertRaisesRegex(ResearchError,'read-only'):t.api_get(action='edit')
        with self.assertRaisesRegex(ResearchError,'Cross-origin'):t.get('https://other.test/')


class LocalTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'workspace/tests').mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'workspace/tests');self.root=Path(self.tmp.name)
        self.wiki=WikiStore(self.root/'wiki.db')
    def tearDown(self):self.tmp.cleanup()
    def test_historical_citations_survive_update(self):
        self.wiki.put(page());old=self.wiki.search('IGCF')[0]
        self.wiki.put(page(rev=9));new=self.wiki.search('IGCF')[0]
        self.assertNotEqual(old['snapshot'],new['snapshot'])
        old=self.wiki.read(old['section_id'])
        self.assertFalse(old['is_current_local_selection']);self.assertIn('oldid=4',old['citation'])
        self.assertTrue(new['is_current_local_selection'])
    def test_failed_update_is_atomic(self):
        self.wiki.put(page());before=self.wiki.search('IGCF')[0]
        bad=page(rev=9);bad['approval']={}
        with self.assertRaises(KeyError):self.wiki.put(bad)
        self.assertEqual(self.wiki.search('IGCF')[0]['snapshot'],before['snapshot'])
    def test_stale_cache_and_missing_page(self):
        self.wiki.put(page())
        class Broken:
            def fetch(self,title):raise ResearchError('offline')
        report=self.wiki.sync(Broken(),['A'],max_depth=0)
        self.assertEqual(report['status'],'incomplete');self.assertEqual(self.wiki.search('IGCF')[0]['cache_status'],'stale')
        class Removed:
            def fetch(self,title):raise MissingPage('deleted')
        self.wiki.sync(Removed(),['A'],max_depth=0)
        self.assertEqual(self.wiki.search('IGCF'),[])
    def test_cap_and_depth_report(self):
        class Client:
            def fetch(self,title):return page(title,pid=1 if title=='A' else 2,links=['B','C'])
        r=self.wiki.sync(Client(),['A'],max_pages=1,max_depth=1)
        self.assertEqual(len(r['imported']),1);self.assertEqual(len(r['pending']),2);self.assertEqual(r['status'],'incomplete')
        r=self.wiki.sync(Client(),['A'],max_pages=2,max_depth=0)
        self.assertTrue(any(x['reason']=='depth limit' for x in r['skipped']))
    def test_redirect_deduplication(self):
        class Client:
            def fetch(self,title):
                p=page('Canonical');p['requested_title']=title;return p
        r=self.wiki.sync(Client(),['Alias','Canonical'])
        self.assertEqual(len(r['imported']),1);self.assertEqual(self.wiki.status()['pages'],1)
    def test_interruption_checkpoints_current_page(self):
        class Interrupted:
            def fetch(self,title):raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.wiki.sync(Interrupted(),['A'])
        report=self.wiki.status()['last_sync']
        self.assertTrue(report['interrupted']);self.assertEqual(report['status'],'incomplete')
        self.assertEqual(report['pending'][0]['title'],'A')
    def test_independent_child_approval_and_removal(self):
        class Client:
            def fetch(self,title):
                p=page(title,1 if title=='A' else 2,links=['B'] if title=='A' else [])
                if title=='B':p.update(selection='latest_fallback',revision=9,approval={'status':'absent','checked_at':'2026-01-02','reason':'none'})
                return p
        report=self.wiki.sync(Client(),['A'],max_pages=2,max_depth=1)
        self.assertEqual(report['selection_counts'],{'approved':1,'latest_fallback':1})
        self.assertEqual(self.wiki.status()['approval_counts'],{'approved':1,'absent':1})
        p=page('A',rev=9);p.update(selection='latest_fallback',approval={'status':'absent','checked_at':'2026-01-02'})
        self.wiki.put(p)
        self.assertEqual(self.wiki.status()['approval_counts'],{'absent':2})
    def test_scoped_sync_excludes_old_pilot_pages_but_keeps_citations(self):
        self.wiki.put(page('Unrelated',pid=99))
        old=self.wiki.search('IGCF')[0]['section_id']
        class Client:
            def fetch(self,title):
                return page(title,pid=1 if title=='Root' else 2,links=['Child'] if title=='Root' else ['Root'])
        report=self.wiki.sync(Client(),['Root'],scoped=True,max_depth=10)
        self.assertEqual([p['title'] for p in report['imported']],['Root','Child'])
        self.assertTrue(report['scope_activated']);self.assertEqual(report['status'],'complete_for_scope')
        status=self.wiki.status()
        self.assertEqual(status['pages'],3);self.assertEqual(status['searchable_pages'],2)
        self.assertEqual({h['title'] for h in self.wiki.search('IGCF')},{'Root','Child'})
        self.assertEqual(self.wiki.read(old)['title'],'Unrelated')
    def test_incomplete_scope_does_not_replace_previous_scope(self):
        class Client:
            def fetch(self,title):return page(title,pid=1 if title=='Root' else 2,links=['Child'] if title=='New' else [])
        self.wiki.sync(Client(),['Root'],scoped=True)
        report=self.wiki.sync(Client(),['New'],scoped=True,max_pages=1)
        self.assertFalse(report['scope_activated'])
        self.assertEqual(self.wiki.status()['active_scope']['roots'],['Root'])
        self.assertEqual({h['title'] for h in self.wiki.search('IGCF')},{'Root'})
    def test_missing_root_cannot_activate_an_empty_scope(self):
        class Missing:
            def fetch(self,title):raise MissingPage(title)
        report=self.wiki.sync(Missing(),['Root'],scoped=True)
        self.assertEqual(report['status'],'incomplete');self.assertFalse(report['scope_activated'])
        self.assertEqual(report['unavailable_roots'],['Root'])
    def test_duplicate_frontier_at_limit_is_complete(self):
        class Client:
            def fetch(self,title):
                p=page('Canonical');p['requested_title']=title;return p
        report=self.wiki.sync(Client(),['Alias','Canonical'],max_pages=1,scoped=True)
        self.assertEqual(report['status'],'complete_for_scope');self.assertEqual(report['pending'],[])
    def test_scoped_depth_limit_records_missing_child(self):
        class Client:
            def fetch(self,title):return page(title,links=['Child'])
        report=self.wiki.sync(Client(),['Root'],max_depth=0,scoped=True)
        self.assertEqual(report['status'],'incomplete');self.assertFalse(report['scope_activated'])
        self.assertEqual(report['skipped'][0]['title'],'Child')
    def test_raw_source_and_alias_search(self):
        p=page('Canonical');p['requested_title']='Alternate';self.wiki.put(p)
        hit=self.wiki.search('Alternate')[0]
        source=self.wiki.source(hit['snapshot']);self.assertEqual(source['text'],'IGCF')
        self.assertIn('<h2',self.wiki.source(hit['snapshot'],format='html')['text'])
        with self.assertRaises(ResearchError):self.wiki.source(hit['snapshot'],format='execute')
    def test_mathml_fraction_and_indices(self):
        sections,warnings=extract_sections('<math><mfrac><msub><mi>X</mi><mi>t</mi></msub><msup><mi>Y</mi><mn>2</mn></msup></mfrac></math>')
        self.assertIn('(X_(t))/(Y^(2))',sections[0]['text'])
        self.assertEqual(warnings[0]['kind'],'mathml_conversion_requires_visual_check')
    def test_parameterized_fts_and_windows(self):
        self.wiki.put(page())
        self.assertEqual(self.wiki.search('IGCF OR nonexistent'),[])
        s=self.wiki.search('"IGCF"')[0]
        self.assertEqual(self.wiki.read(s['section_id'],length=4)['text'],'IGCF')
        with self.assertRaises(ResearchError):self.wiki.read(s['section_id'],offset=-1)
        with self.assertRaises(ResearchError):self.wiki.search('***')
    def test_extraction_keeps_table_math_and_warnings(self):
        sections,warnings=extract_sections('<h2 id="eq">Equation</h2><p>A<sub>t</sub> = B<sup>2</sup></p><table><tr><th>Country</th><th>GDP</th></tr><tr><td>A</td><td>12</td></tr></table><span class="mwe-math-element"><math><annotation encoding="application/x-tex">x+y</annotation></math></span><img src="eq.png" alt="Equation 2"><script>evil()</script>')
        text=''.join(x['text'] for x in sections)
        self.assertIn('A_(t)',text);self.assertIn('B^(2)',text);self.assertIn('A | 12 |',text);self.assertIn('[Math: x+y]',text)
        self.assertNotIn('evil',text);self.assertEqual(sections[0]['anchor'],'eq')
        self.assertEqual(warnings[0]['kind'],'visual_not_transcribed')
    def test_embedded_dependencies_not_labeled_approved(self):
        p=page();p['content']['templates']=[{'title':'Template:Equation'}]
        self.wiki.put(p)
        self.assertTrue(any(w['kind']=='embedded_dependency_approval_unverified' for w in self.wiki.search('IGCF')[0]['warnings']))
    def test_workspace_overlap_rejected(self):
        f=self.root/'config.json';f.write_text(json.dumps({'workspace':'source/cache','code_root':'source','results_registry':'pilot.json'}))
        with self.assertRaisesRegex(ResearchError,'overlaps'):Config(f)


class CodeTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'workspace/tests').mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'workspace/tests');self.root=Path(self.tmp.name)
        self.source=self.root/'source';self.source.mkdir()
        self.file=self.source/'Economy.Forecast.vb'
        self.file.write_text('Public Sub Growth()\nDim GDP As Double\nGDP = 4\nIf GDP = 3 Then\nGDP = GDP + 1\nEnd If\n\' GDP comment\nPrint("GDP")\nGDPPC = 5\nEnd Sub\n',encoding='utf-8')
        (self.source/'obj').mkdir();(self.source/'obj'/'generated.vb').write_text('GDP = 999')
        (self.source/'Thing.Designer.vb').write_text('GDP = 888')
        self.code=CodeStore(self.root/'code.db');self.result=self.code.index(self.source)
    def tearDown(self):self.tmp.cleanup()
    def test_exact_references_ignore_comments_strings_and_longer_names(self):
        result=self.code.search('GDP',references=True)
        self.assertEqual([h['line'] for h in result['hits']],[2,3,4,5])
        self.assertEqual(result['hits'][0]['kind'],'declaration_or_signature_candidate')
        self.assertEqual(result['hits'][1]['kind'],'assignment_candidate')
        self.assertEqual(result['hits'][2]['kind'],'lexical_occurrence')
        self.assertEqual(self.result['files'],1);self.assertEqual(len(self.result['excluded']),2)
    def test_routine_and_phase(self):
        r=self.code.find_routines('growth')[0];v=self.code.read_routine(r['id'])
        self.assertEqual(v['start'],1);self.assertEqual(v['end'],10);self.assertIsNone(v['next_offset'])
        self.assertIn('first-year',v['phase']);self.assertEqual(self.code.search('GDP',references=True)['hits'][0]['routine_id'],r['id'])
    def test_snapshots_preserve_source(self):
        sid=self.result['snapshot'];self.file.write_text('GDP = 10\n')
        self.assertFalse(self.code.read('Economy.Forecast.vb',snapshot=sid)['local_source_matches_snapshot'])
        new=self.code.index(self.source);self.assertNotEqual(sid,new['snapshot'])
        self.assertIn('GDP = 4',self.code.read('Economy.Forecast.vb',snapshot=sid)['text'])
        self.assertEqual(self.code.search('GDP',references=True)['total'],1)
        self.assertEqual(self.code.search('GDP',references=True,snapshot=sid)['total'],4)
    def test_literal_search_preserves_punctuation_and_case(self):
        self.assertEqual([h['line'] for h in self.code.search('GDP = 4',literal=True)['hits']],[3])
        self.assertEqual(self.code.search('gdp = 4',literal=True)['total'],0)
        self.assertEqual(self.code.search('Print("GDP")',literal=True)['hits'][0]['line'],8)
        with self.assertRaises(ResearchError):self.code.search('',literal=True)
    def test_navigation_limits(self):
        r=self.code.search('GDP',limit=2,references=True);self.assertEqual(r['next_offset'],2)
        self.assertEqual(len(self.code.search('GDP',limit=2,offset=2,references=True)['hits']),2)
        with self.assertRaises(ResearchError):self.code.read('../outside.vb')
        with self.assertRaises(ResearchError):self.code.read('Economy.Forecast.vb',start=0)
        with self.assertRaises(ResearchError):self.code.search('GDP OR I',references=True)
    def test_unchanged_index_and_read_only_sources(self):
        before=self.file.read_bytes();sid=self.code.index(self.source)['snapshot']
        self.assertEqual(self.result['snapshot'],sid);self.assertEqual(before,self.file.read_bytes())
        self.assertFalse(any(p.suffix=='.db' for p in self.source.rglob('*')))
    def test_assignment_nested_indices_and_comparisons(self):
        self.assertTrue(assignment_lhs('IDS(R%, IS%) = IGCF(R%)', 'IDS'))
        self.assertTrue(assignment_lhs('IDS(f(R%)) += 1', 'IDS'))
        self.assertFalse(assignment_lhs('If IDS(R%) = 1 Then', 'IDS'))
        self.assertFalse(assignment_lhs('IDS_OTHER = 1', 'IDS'))
        self.assertTrue(assignment_lhs('Year% = 1', 'Year'))
        self.assertEqual(clean_vb('Print("a""GDP") \' GDP'),'Print(  ) ')
    def test_underscores_are_part_of_identifiers(self):
        self.file.write_text('GDP_GROWTH = 1\nGDP GROWTH = 2\nOTHER_GDP_GROWTH = 3\n')
        self.code.index(self.source)
        result=self.code.search('GDP_GROWTH',references=True)
        self.assertEqual(result['total'],1);self.assertEqual(result['hits'][0]['line'],1)
    def test_unclosed_routine_warning(self):
        r=routines(['Sub A()', 'GDP=1', 'Sub B()', 'End Sub'])
        self.assertTrue(r[0]['boundary_warning']);self.assertEqual(r[0]['end'],2)


if __name__=='__main__':unittest.main()
