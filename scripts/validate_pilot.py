"""Local pilot validation; no IFs forecasting. Outputs only under this project/workspace."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from fastparquet import core
from ifs_analysis import Registry, Reader, check_equality, rank_gdp, reconcile_investment
from ifs_analysis.jobs import run_job, write_json, engine_identity
from ifs_analysis.registry import readonly, fingerprint

ROOT = Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--registry',type=Path,default=ROOT/'resources/pilot.json')
    p.add_argument('--reference-tool',type=Path,default=ROOT.parent/'ifs-872/Code.Ifs-Translation/src/ParquetTools/bin/Debug/net8.0')
    p.add_argument('--reference-exports',type=Path,default=ROOT.parent/'analysis/investment-reconciliation')
    args=p.parse_args()
    registry=Registry(args.registry)
    root=ROOT/'workspace/validation';root.mkdir(parents=True,exist_ok=True)
    copied=root/'reference-reader';copied.mkdir(exist_ok=True)
    tool_fingerprints=[]
    for name in ['ParquetTools.dll','ParquetTools.deps.json','ParquetTools.runtimeconfig.json','Parquet.dll']:
        source=args.reference_tool/name
        tool_fingerprints.append(fingerprint(source))
        shutil.copyfile(source,copied/name)
    all_inputs=list(dict.fromkeys(p for key in registry.config['datasets'] for p in registry.input_paths(key)))
    before=[fingerprint(p) for p in all_inputs]
    directory_before={str(registry.dataset(k)['path'].parent): sorted(p.name for p in registry.dataset(k)['path'].parent.iterdir()) for k in registry.config['datasets']}
    report={'status':'running','engine':engine_identity(),'reference_tool':tool_fingerprints,'inputs_before':before,'datasets':{}}
    for dataset in registry.config['datasets']:
        print(f'Validating {dataset}...',flush=True)
        reader=Reader(registry,dataset)
        reference_results={}
        original=core.read_plain
        for variable in ['GDP','I','INVS']:
            selection=reader.extract(variable).require_complete()
            assert selection.coverage['decoder']=='legacy_int16_worker'
            assert core.read_plain is original, 'Decoder modified parent fastparquet state'
            with readonly(reader.path) as db:
                blob=db.execute('SELECT Data FROM ifs_var_blob WHERE VariableName=?',(variable,)).fetchone()[0]
            payload=(copied/f'{dataset}-{variable}.parquet').resolve()
            textfile=(copied/f'{dataset}-{variable}.txt').resolve()
            payload.write_bytes(blob)
            proc=subprocess.run(['dotnet',str(copied/'ParquetTools.dll'),str(payload),str(textfile)],capture_output=True,text=True,timeout=90,cwd=copied)
            if proc.returncode: raise RuntimeError(proc.stderr)
            dims=[d['column'] for d in selection.metadata['dimensions']]
            rows=[]
            for line in textfile.read_text().splitlines():
                suffix='-'+str(payload)
                assert line.endswith(suffix)
                fields=line[:-len(suffix)].split('-',len(dims))
                rows.append([*[int(v) for v in fields[:-1]],float(np.float32(fields[-1]))])
            reference=pd.DataFrame(rows,columns=dims+['value']).sort_values(dims).reset_index(drop=True)
            actual=selection.table.loc[selection.table.year<2029,dims+['value']].reset_index(drop=True)
            pd.testing.assert_frame_equal(reference,actual,check_dtype=False,check_exact=True)
            reference_results[variable]={'matched_rows':len(reference),'comparison':'exact decoded float32 values and dimension keys','reference_years':'2022-2028 (existing tool cutoff)'}
        world,evidence=reconcile_investment(reader)
        export=args.reference_exports/f'{dataset}_world.csv'
        old=pd.read_csv(export)
        assert list(old.columns)==list(world.columns)
        np.testing.assert_allclose(world.to_numpy(),old.to_numpy(),rtol=1e-12,atol=1e-8)
        world.to_csv(root/f'{dataset}-reconciliation.csv',index=False,float_format='%.17g')
        equality,eq=check_equality(reader,'I','IGCF',atol=0.001,rtol=1e-6)
        ranking,rk=rank_gdp(reader,first_year=2022,last_year=2050,metric='cagr')
        report['datasets'][dataset]={'reference_reader':reference_results,
            'reconciliation_reference':fingerprint(export),'reconciliation_years':len(world),
            'reconciliation_max_absolute_export_difference':float(np.max(np.abs(world.to_numpy()-old.to_numpy()))),
            'max_country_forecast_reconciliation_error':evidence['max_country_forecast_reconciliation_error'],
            'equality':{'years':len(equality),'equal_years':int(equality.equal.sum()),'failing_years':eq['failing_years']},
            'ranking':{'period':[2022,2050],'metric':'cagr','countries':len(ranking),'top5':ranking.head(5).to_dict(orient='records')}}
        # Exercise full CLI-equivalent artifacts, then replay one script with source checks.
        job=run_job(args.registry,dataset,'gdp-ranking',{'first_year':2022,'last_year':2050,'metric':'cagr'},ROOT/'workspace/jobs')
        replay=subprocess.run([sys.executable,'-B',str(job/'analysis.py')],capture_output=True,text=True,timeout=180)
        if replay.returncode: raise RuntimeError(replay.stderr)
        report['datasets'][dataset]['ranking_job']=str(job)
        report['datasets'][dataset]['replayed_job']=replay.stdout.strip()
    after=[fingerprint(p) for p in all_inputs]
    assert before==after,'Sources changed'
    directory_after={str(registry.dataset(k)['path'].parent): sorted(p.name for p in registry.dataset(k)['path'].parent.iterdir()) for k in registry.config['datasets']}
    assert directory_before==directory_after,'Source-directory entries changed'
    report.update(status='passed',inputs_after=after,source_directory_entries_unchanged=True,
                  distinct_result_file_hashes=len({f['sha256'] for f in before if f['path'].endswith('.run.db')}))
    write_json(root/'validation.json',report)
    print(root/'validation.json')

if __name__=='__main__': main()
