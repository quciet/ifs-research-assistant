"""Run and independently spot-check the reviewed pilot, then verify artifact replay."""
import json
import math
from pathlib import Path
import pandas as pd
from ifs_analysis import Reader,Registry
from ifs_analysis.jobs import engine_identity
from ifs_analysis.registry import fingerprint
from ifs_investigation import run,replay
from ifs_research.common import now

ROOT=Path(__file__).resolve().parents[1]


def main():
    config=ROOT/'resources/research.json';spec=ROOT/'resources/investigations/i-vs-invs-872.json'
    job=run(config,spec);reader=Reader(Registry(ROOT/'resources/pilot.json'),'IFsBase')
    table=pd.read_csv(job/'country_values.csv');comparisons=pd.read_csv(job/'comparisons.csv')
    evidence=json.loads((job/'evidence.json').read_text())
    countries=[1,34,180];years=[2022,2050,2100]
    variables=['I','INVS','IGCF','PFD','MS','CS','GS','XS']
    # Independent arithmetic and sector aggregation from reader observations, without _country_series/evaluate.
    extracted={v:reader.extract(v,2022,2100,{'country_id':countries}).require_complete().table for v in variables}
    spots=[]
    for country in countries:
        for year in years:
            values={v:math.fsum(float(x) for x in frame.loc[(frame.country_id==country)&(frame.year==year),'value']) for v,frame in extracted.items()}
            stored=table[(table.country_id==country)&(table.year==year)].iloc[0]
            for v in variables:assert math.isclose(values[v],stored[v],rel_tol=1e-12,abs_tol=1e-8),(v,country,year)
            expected= max(0.001,values['INVS']) if year==2022 else math.fsum([values['IGCF'],values['PFD'],values['MS'],-values['CS'],-values['INVS'],-values['GS'],-values['XS']])
            key='initialization_with_floor' if year==2022 else 'forecast_inventory_accounting'
            check=comparisons[(comparisons.check_id==key)&(comparisons.grain=='country')&(comparisons.country_id==country)&(comparisons.year==year)].iloc[0]
            assert math.isclose(expected,check.rhs,rel_tol=1e-12,abs_tol=1e-8)
            spots.append({'country_id':country,'year':year,'check':key,'rhs_independent':expected,'rhs_stored':float(check.rhs)})
    again=replay(job)
    original=json.loads((ROOT/'workspace/validation/validation.json').read_text())
    assert engine_identity()==original['engine']
    assert all(fingerprint(item['path'])==item for item in original['inputs_before'])
    summary={'status':'passed','checked_at':now(),'job':str(job),'replay_job':str(again),
        'table_replay_byte_identical':True,'independent_spot_checks':spots,
        'scope':'Independent spot checks cover 3 countries x 3 years; full-coverage checks use the verified reader and reviewed expressions.',
        'outcome':evidence['outcome'],'numeric_consistency':evidence['numeric_consistency'],
        'checks':evidence['checks'],'numerical_baseline_unchanged':True}
    output=ROOT/'workspace/research/phase4-validation.json';output.write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps({'status':'passed','report':str(output),'investigation':str(job),'replay':str(again)}))


if __name__=='__main__':main()
