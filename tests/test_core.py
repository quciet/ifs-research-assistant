"""Synthetic fixtures only; no access to IFs source files in this suite."""
import io
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import warnings
import numpy as np
import pandas as pd
import fastparquet
from fastparquet import core
from ifs_analysis import Registry, Reader, AnalysisError, check_equality, rank_gdp
from ifs_analysis.jobs import run_job
from ifs_analysis.registry import readonly, fingerprint

ROOT = Path(__file__).resolve().parents[1]

class AnalysisTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'workspace/tests').mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT/'workspace/tests')
        self.root = Path(self.tmp.name)
        (self.root/'sources').mkdir()
        self.db = self.root/'sources/test.db'
        with closing(sqlite3.connect(self.db)) as c, c:
            c.executescript('''
            CREATE TABLE ifs_var (Name TEXT PRIMARY KEY, DisplayName TEXT, Currency TEXT, Aggregation TEXT);
            CREATE TABLE ifs_dim (Id INTEGER, Name TEXT);
            CREATE TABLE ifs_var_dim (VariableName TEXT, Seq INTEGER, DimensionId INTEGER);
            CREATE TABLE ifs_dim_bucket (DimensionId INTEGER, Seq INTEGER, Name TEXT);
            CREATE TABLE ifs_var_blob (VariableName TEXT PRIMARY KEY, Data BLOB);
            ''')
            c.executemany('INSERT INTO ifs_dim VALUES (?,?)', [(0,'Time'),(1,'Region'),(2,'Sector')])
            c.executemany('INSERT INTO ifs_dim_bucket VALUES (?,?,?)',
                [(0,y,str(y)) for y in (2022,2023,2024)] + [(1,1,'A'),(1,2,'B'),(1,99,'World'),(2,1,'S1'),(2,2,'S2')])
        members={'members':[{'id':i,'name':n,'kind':'country_or_territory'} for i,n in [(1,'A'),(2,'B')]]}
        (self.root/'countries.json').write_text(json.dumps(members))
        sem={'unit_family':'money','sum_dimensions':[]}
        config={'schema_version':1,'country_membership':'countries.json',
                'datasets':{'test':{'path':'sources/test.db','encoding':'standard'}},
                'variable_semantics':{v:dict(sem) for v in ['GDP','X','Y','SECTOR']}}
        config['variable_semantics']['SECTOR']['sum_dimensions']=[2]
        config['variable_semantics']['SECTOR']['summed_dimension_buckets']={'2': {'1':'S1','2':'S2'}}
        self.config=config
        self.registry_path=self.root/'registry.json'
        self.save_config()
        rows=[(2022,1,100.),(2022,2,50.),(2022,99,150.),
              (2023,1,110.),(2023,2,65.),(2023,99,175.),
              (2024,1,121.),(2024,2,80.),(2024,99,201.)]
        self.frame=pd.DataFrame(rows,columns=['0','1','v'])
        for v in ['GDP','X','Y']: self.put(v,self.frame)
        sector=pd.DataFrame([(y,c,s,val/2) for y,c,val in rows for s in (1,2)],columns=['0','1','2','v'])
        self.put('SECTOR',sector)

    def tearDown(self): self.tmp.cleanup()

    def save_config(self): self.registry_path.write_text(json.dumps(self.config))

    def put(self, name, frame, aggregation='SUM', currency='1'):
        frame=frame.copy()
        for col in frame:
            frame[col]=frame[col].astype('float32' if col=='v' else 'int16')
        out=self.root/'fixture.parquet'
        fastparquet.write(str(out),frame,write_index=False,compression='SNAPPY')
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute('INSERT OR REPLACE INTO ifs_var VALUES (?,?,?,?)',(name,name,currency,aggregation))
            c.execute('DELETE FROM ifs_var_dim WHERE VariableName=?',(name,))
            c.executemany('INSERT INTO ifs_var_dim VALUES (?,?,?)',[(name,i+1,int(col)) for i,col in enumerate(frame.columns) if col!='v'])
            c.execute('INSERT OR REPLACE INTO ifs_var_blob VALUES (?,?)',(name,out.read_bytes()))

    def reader(self): return Reader(Registry(self.registry_path),'test')

    def test_named_dimensions_and_filters(self):
        s=self.reader().extract('SECTOR',2023,2024,{'country_id':[2],'dim_2':[1]})
        self.assertTrue(s.coverage['complete']); self.assertEqual(len(s.table),2)
        self.assertEqual(s.table.country.tolist(),['B','B']); self.assertIn('dim_2_label',s.table)

    def test_world_excludes_precomputed_group(self):
        table,e=check_equality(self.reader(),'X','Y',atol=0,rtol=0)
        self.assertEqual(table.x.tolist(),[150,175,201]); self.assertTrue(e['all_equal'])
        self.assertEqual(e['x']['excluded_region_ids'],[99])

    def test_sector_sum_matches_total(self):
        table,e=check_equality(self.reader(),'X','SECTOR',atol=0,rtol=0)
        self.assertTrue(e['all_equal'])

    def test_perturbed_identity_reports_year(self):
        f=self.frame.copy(); f.loc[3,'v']+=1; self.put('Y',f)
        table,e=check_equality(self.reader(),'X','Y',atol=.01,rtol=0)
        self.assertEqual(e['failing_years'],[2023])

    def test_missing_row_is_reported_and_analysis_rejected(self):
        self.put('X',self.frame.drop(index=3))
        self.assertFalse(self.reader().extract('X').coverage['complete'])
        with self.assertRaisesRegex(AnalysisError,'Incomplete'): check_equality(self.reader(),'X','Y',atol=0,rtol=0)

    def test_missing_entire_year_rejected(self):
        self.put('GDP',self.frame[self.frame['0']!=2023])
        with self.assertRaisesRegex(AnalysisError,'Incomplete'): rank_gdp(self.reader(),first_year=2022,last_year=2024,metric='absolute')

    def test_duplicate_keys_rejected(self):
        self.put('X',pd.concat([self.frame,self.frame.iloc[:1]]))
        with self.assertRaisesRegex(AnalysisError,'Duplicate'): self.reader().extract('X')

    def test_invalid_dimension_rejected(self):
        f=self.frame.copy();f.loc[0,'1']=44;self.put('X',f)
        with self.assertRaisesRegex(AnalysisError,'Invalid dimension'): self.reader().extract('X')

    def test_nonfinite_values_rejected(self):
        for value in [np.nan,np.inf]:
            f=self.frame.copy();f.loc[0,'v']=value;self.put('X',f)
            with self.assertRaisesRegex(AnalysisError,'Incomplete'): check_equality(self.reader(),'X','Y',atol=0,rtol=0)

    def test_invalid_selections(self):
        for args in [('X',2025,2026,{}),('X',2024,2022,{}),('X',2022,2024,{'oops':[1]}),('X',2022,2024,{'country_id':[33]})]:
            with self.assertRaises(AnalysisError): self.reader().extract(*args)
        with self.assertRaises(AnalysisError): self.reader().extract('NOT_A_VARIABLE')

    def test_unsupported_aggregation(self):
        self.put('X',self.frame,aggregation='POP')
        with self.assertRaisesRegex(AnalysisError,'SUM'): check_equality(self.reader(),'X','Y',atol=0,rtol=0)

    def test_unknown_semantics(self):
        del self.config['variable_semantics']['X'];self.save_config()
        with self.assertRaisesRegex(AnalysisError,'semantics'): check_equality(self.reader(),'X','Y',atol=0,rtol=0)

    def test_unreviewed_extra_dimension(self):
        self.config['variable_semantics']['SECTOR']['sum_dimensions']=[]; self.save_config()
        with self.assertRaisesRegex(AnalysisError,'dimensions'): check_equality(self.reader(),'SECTOR','Y',atol=0,rtol=0)

    def test_extra_total_sector_rejected(self):
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute("UPDATE ifs_dim_bucket SET Name='Total' WHERE DimensionId=2 AND Seq=2")
        with self.assertRaisesRegex(AnalysisError,'summed dimension buckets'):
            check_equality(self.reader(),'SECTOR','Y',atol=0,rtol=0)

    def test_currency_mismatch(self):
        self.put('Y',self.frame,currency='PPP')
        with self.assertRaisesRegex(AnalysisError,'incompatible'): check_equality(self.reader(),'X','Y',atol=0,rtol=0)

    def test_growth_metrics(self):
        for metric,expected in [('absolute',30),('percent',60),('cagr',(1.6**.5-1)*100)]:
            t,e=rank_gdp(self.reader(),first_year=2022,last_year=2024,metric=metric)
            self.assertEqual(t.iloc[0].country,'B');self.assertAlmostEqual(t.iloc[0].growth,expected)
            self.assertEqual(len(t),2)

    def test_zero_start_excluded_but_retained(self):
        f=self.frame.copy();f.loc[0,'v']=0;self.put('GDP',f)
        t,e=rank_gdp(self.reader(),first_year=2022,last_year=2024,metric='percent')
        self.assertEqual(e['excluded_countries'],['A']);self.assertTrue(pd.isna(t.iloc[-1].growth))
        t,e=rank_gdp(self.reader(),first_year=2022,last_year=2024,metric='absolute')
        self.assertEqual(t.iloc[0].country,'A')

    def test_invalid_growth_period(self):
        with self.assertRaises(AnalysisError): rank_gdp(self.reader(),first_year=2024,last_year=2022,metric='cagr')

    def test_invalid_tolerance(self):
        for tol in [-1,float('nan'),float('inf')]:
            with self.assertRaises(AnalysisError): check_equality(self.reader(),'X','Y',atol=tol,rtol=0)

    def test_no_global_decoder_patch(self):
        original=core.read_plain;self.reader().extract('GDP');self.assertIs(core.read_plain,original)

    def test_read_only_and_fingerprints(self):
        before=fingerprint(self.db)
        with readonly(self.db) as db:
            with self.assertRaises(sqlite3.OperationalError): db.execute('DELETE FROM ifs_var')
        self.reader().extract('GDP')
        self.assertEqual(before,fingerprint(self.db))
        self.assertFalse(Path(str(self.db)+'-journal').exists())

    def test_reject_live_sidecar(self):
        Path(str(self.db)+'-wal').write_bytes(b'live')
        with self.assertRaisesRegex(AnalysisError,'sidecar'): self.reader().extract('GDP')

    def test_payload_budget_rejects_instead_of_truncating(self):
        self.config['max_payload_rows']=2;self.save_config()
        with self.assertRaisesRegex(AnalysisError,'budget'): self.reader().extract('GDP')

    def test_mismatched_membership(self):
        p=self.root/'countries.json';s=json.loads(p.read_text());s['members'][0]['name']='Wrong';p.write_text(json.dumps(s))
        with self.assertRaisesRegex(AnalysisError,'membership'): rank_gdp(self.reader(),first_year=2022,last_year=2024,metric='absolute')

    def test_artifact_replay(self):
        job=run_job(self.registry_path,'test','gdp-ranking',{'first_year':2022,'last_year':2024,'metric':'percent'},self.root/'jobs')
        proc=subprocess.run([sys.executable,'-B',str(job/'analysis.py')],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        manifest=json.loads((job/'manifest.json').read_text())
        self.assertEqual(manifest['status'],'complete')
        self.assertTrue((job/'execution.log').exists())

    def test_replay_rejects_changed_input(self):
        job=run_job(self.registry_path,'test','gdp-ranking',{'first_year':2022,'last_year':2024,'metric':'percent'},self.root/'jobs')
        f=self.frame.copy();f.loc[0,'v']=23;self.put('GDP',f)
        proc=subprocess.run([sys.executable,'-B',str(job/'analysis.py')],capture_output=True,text=True)
        self.assertNotEqual(proc.returncode,0);self.assertIn('fingerprints',proc.stderr)

    def test_output_source_overlap_rejected(self):
        with self.assertRaisesRegex(AnalysisError,'overlaps'):
            run_job(self.registry_path,'test','extract',{'variable':'X'},self.db.parent)

if __name__=='__main__': unittest.main()
