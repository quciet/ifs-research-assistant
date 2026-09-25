"""Phase 4 tests use an unrelated synthetic resource-balance implementation."""
import copy
import json
from pathlib import Path
import unittest
import test_core
from ifs_research import Research
from ifs_research.common import ResearchError,digest
from ifs_analysis.registry import fingerprint
from ifs_investigation.engine import evaluate,validate,classify
from ifs_investigation.jobs import run,replay,draft


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_core.AnalysisTests('test_named_dimensions_and_filters');self.fixture.setUp()
        f=self.fixture;self.root=f.root
        f.put('GDP',f.frame.assign(v=f.frame.v*2))
        source=self.root/'sources'/'Balance.Forecast.vb'
        source.write_text('Public Sub ResourceBalance()\nGDP = X + Y\nEnd Sub\n',encoding='utf-8')
        self.config=self.root/'research.json'
        self.config.write_text(json.dumps({'workspace':'work','code_root':'sources','results_registry':'registry.json'}))
        self.research=Research(self.config);self.research.code.index(self.root/'sources')
        view=self.research.code.read('Balance.Forecast.vb',1,3)
        self.spec={'schema_version':1,'question':'How does this synthetic resource balance work?',
            'dataset':'test','review_status':'reviewed','source_snapshot':view['snapshot'],
            'code_evidence':[{'id':'balance','path':view['path'],'start':1,'end':3,'file_sha256':view['sha256'],'text_sha256':digest(view['text'])}],
            'code_explanation':[{'text':'GDP is assigned X plus Y in this synthetic fixture.','code_evidence':['balance']}],
            'wiki_sections':[], 'preconditions':[{'description':'Synthetic values generated at the cited assignment.','status':'established','evidence':'Fixture construction in test_investigation.py'}],
            'checks':[{'id':'resource_balance','purpose':'implemented_relation','stage':'all','lhs':{'terms':{'GDP':1}},'rhs':{'terms':{'X':1,'Y':1}},'atol':0,'rtol':0,'code_evidence':['balance'],'explanation':'Reviewed synthetic resource balance.'},
                      {'id':'observation','purpose':'observation','stage':'all','lhs':{'terms':{'GDP':1}},'rhs':{'terms':{'X':1}},'atol':0,'rtol':0,'code_evidence':[],'explanation':'A difference alone is not a failed requirement.'}]}
        self.path=self.root/'spec.json';self.save()
    def tearDown(self):self.fixture.tearDown()
    def save(self):self.path.write_text(json.dumps(self.spec))
    def provenance(self,match=True):
        p=self.root/'provenance.json'
        p.write_text(json.dumps({'source_snapshot':self.research.code.current() if match else 'different',
            'dataset_sha256':fingerprint(self.fixture.db)['sha256'],'basis':'Synthetic fixture generated from reviewed construction.'}))
        self.spec['version_evidence']=str(p);self.save()
    def test_supported_unrelated_relationship_despite_observed_difference(self):
        values,checks,e=evaluate(self.fixture.reader(),self.spec,'documented_match')
        self.assertEqual(e['outcome'],'supported')
        self.assertEqual(len(values),6);self.assertNotIn(99,values.country_id.tolist())
        self.assertEqual(e['checks'][1]['outside_tolerance'],6)
    def test_unknown_version_still_explains_code_and_numbers(self):
        _,_,e=evaluate(self.fixture.reader(),self.spec)
        self.assertEqual(e['outcome'],'insufficient_evidence');self.assertTrue(e['code_explanation'])
        self.assertEqual(e['checks'][0]['outside_tolerance'],0)
    def test_perturbed_fixture_detected_even_if_world_cancels(self):
        f=self.fixture;frame=f.frame.copy();frame.loc[(frame['0']==2023)&(frame['1']==1),'v']+=10
        frame.loc[(frame['0']==2023)&(frame['1']==2),'v']-=10;f.put('Y',frame)
        _,checks,e=evaluate(f.reader(),self.spec,'documented_match')
        self.assertEqual(e['outcome'],'potential_inconsistency');self.assertEqual(e['checks'][0]['outside_tolerance'],2)
        self.assertTrue(checks[(checks.check_id=='resource_balance')&(checks.grain=='selected_country_total')].within_tolerance.all())
    def test_unverified_precondition_prevents_failure_verdict(self):
        self.spec['preconditions'][0]['status']='unknown'
        self.fixture.put('Y',self.fixture.frame.assign(v=self.fixture.frame.v+10))
        _,_,e=evaluate(self.fixture.reader(),self.spec,'documented_match')
        self.assertEqual(e['outcome'],'insufficient_evidence')
    def test_version_mismatch_takes_priority(self):
        _,_,e=evaluate(self.fixture.reader(),self.spec,'documented_mismatch')
        self.assertEqual(e['outcome'],'incompatible_inputs')
    def test_missing_stage_not_vacuously_supported(self):
        self.spec['period']={'first_year':2023,'last_year':2024};self.spec['checks'][0]['stage']='first_stored_year'
        _,_,e=evaluate(self.fixture.reader(),self.spec,'documented_match')
        self.assertEqual(e['checks'][0]['rows'],0);self.assertEqual(e['outcome'],'insufficient_evidence')
    def test_floor_applied_before_total(self):
        self.spec['checks'][0]['rhs']={'terms':{'Y':1},'floor':90}
        _,checks,_=evaluate(self.fixture.reader(),self.spec)
        world=checks[(checks.check_id=='resource_balance')&(checks.grain=='selected_country_total')]
        self.assertEqual(world.rhs.tolist(),[190,200,211])
    def test_incomplete_data_retains_code_explanation_in_artifact(self):
        self.fixture.put('Y',self.fixture.frame.iloc[1:]);self.save()
        job=run(self.config,self.path);e=json.loads((job/'evidence.json').read_text())
        self.assertEqual(e['outcome'],'insufficient_evidence');self.assertIn('Incomplete',e['numeric_error'])
        self.assertTrue((job/'source-evidence.json').exists());self.assertTrue(e['code_explanation'])
        self.assertFalse((job/'comparisons.csv').exists())
    def test_draft_does_not_turn_expectation_into_requirement(self):
        folder=draft(self.config,'Why is GDP different from X?',['GDP','X'],'test')
        p=json.loads((folder/'investigation.json').read_text())
        self.assertEqual(p['review_status'],'draft');self.assertEqual(p['checks'],[])
        self.assertTrue((folder/'discovery.json').exists())
        with self.assertRaises(ResearchError):run(self.config,folder/'investigation.json')
    def test_replay_and_provenance(self):
        self.provenance();job=run(self.config,self.path);again=replay(job)
        self.assertEqual((job/'comparisons.csv').read_bytes(),(again/'comparisons.csv').read_bytes())
        self.assertEqual(json.loads((job/'evidence.json').read_text())['outcome'],'supported')
        self.assertTrue((job/'implementation'/'ifs_investigation'/'engine.py').exists())
    def test_changed_source_requires_review(self):
        self.provenance();job=run(self.config,self.path)
        (self.root/'sources'/'Balance.Forecast.vb').write_text('GDP = X - Y')
        with self.assertRaisesRegex(ResearchError,'Source review required'):replay(job)
        self.research.code.index(self.root/'sources')
        with self.assertRaisesRegex(ResearchError,'snapshot differs'):run(self.config,self.path)
    def test_changed_saved_data_replay_rejected(self):
        job=run(self.config,self.path);self.fixture.put('Y',self.fixture.frame.assign(v=self.fixture.frame.v+1))
        with self.assertRaisesRegex(ResearchError,'Replay inputs'):replay(job)
    def test_bad_code_citation_rejected(self):
        self.spec['code_evidence'][0]['text_sha256']='not-the-text';self.save()
        with self.assertRaisesRegex(ResearchError,'citation changed'):run(self.config,self.path)
    def test_conditions_observations_and_expression_validation(self):
        bad=copy.deepcopy(self.spec);bad['checks'][0]['rhs']={'python':'import os'}
        with self.assertRaises(ResearchError):validate(bad)
        bad=copy.deepcopy(self.spec);bad['checks'][0]['atol']=-1
        with self.assertRaises(ResearchError):validate(bad)
        bad=copy.deepcopy(self.spec);bad['code_explanation'][0]['code_evidence']=['unknown']
        with self.assertRaises(ResearchError):validate(bad)
        self.spec['country_ids']=[99]
        with self.assertRaises(ResearchError):evaluate(self.fixture.reader(),self.spec)


if __name__=='__main__':unittest.main()
