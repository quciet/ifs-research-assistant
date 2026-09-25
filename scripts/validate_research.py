"""Offline pilot evidence checks. Requires the explicitly synced wiki and indexed IFs 8.72 source."""
from collections import Counter
import json
from pathlib import Path
import sys
from ifs_research import Research
from ifs_research.common import database, digest, now
from ifs_analysis.jobs import engine_identity
from ifs_analysis.registry import fingerprint

ROOT=Path(__file__).resolve().parents[1]


def compact(hit):
    keys=('section_id','snapshot','title','heading','revision','revision_timestamp','citation','selection','approval','fetched_at','cache_status','text','next_offset')
    return {**{k:hit[k] for k in keys},'warning_kinds':sorted({w['kind'] for w in hit['warnings']})}


def main():
    r=Research(ROOT/'resources/research.json')
    status=r.wiki.status();code=r.code.status()
    assert status['pages'] and code['indexed'], 'Run wiki-sync and code-index first'
    report={'checked_at':now(),'status':'running','wiki':{k:status[k] for k in ('pages','searchable_pages','active_scope','active_sections','approval_counts','cache_counts')},
            'source_snapshot':code['snapshot'],'source_files':len(code['files']),
            'coverage_notice':'Bounded pilot corpus, not a complete wiki mirror; lexical code navigation, not compiler binding.'}
    cases=[('investment','IGCF invm','Economics','Exogenous intervention'),
           ('productivity','Cobb Douglas','Economics','Changing Factor Contributions'),
           ('education_linkages','EDYRSCONTRIB','Health','Productivity'),
           ('scenario_setup','Add Scenario Component','Guide to Scenario Analysis in International Futures (IFs)','Prepackaged Scenarios'),
           ('named_variable','GDP','Economics','GDP and GDP per Capita')]
    report['retrieval_examples']=[]
    for label,query,title,heading in cases:
        hits=r.wiki.search(query,10)
        selected=next((h for h in hits if h['title']==title and heading in h['heading']),None)
        assert selected is not None, f'Retrieval regression: {label}'
        full=r.wiki.read(selected['section_id'])
        assert full['revision']==selected['revision'] and str(full['revision']) in full['citation']
        report['retrieval_examples'].append({'case':label,'query':query,'rank':hits.index(selected)+1,'evidence':compact(full)})
    with database(r.wiki.path) as db:
        pages=[json.loads(x[0]) for x in db.execute('SELECT s.payload FROM wiki_snapshots s JOIN wiki_pages p ON p.snapshot=s.id')]
    for p in pages:
        assert digest(json.dumps(p['content'],ensure_ascii=False,sort_keys=True))==p['content_sha256']
        assert p['content']['revid']==p['revision']
        if p['selection']=='approved':assert p['approval']['status']=='approved' and p['approval']['revision']==p['revision']
        else:assert p['approval']['status'] in ('absent','unknown') and p['revision']==p['latest_revision_at_selection']
    report['live_revision_examples']=[{k:p[k] for k in ('title','revision','latest_revision_at_selection','selection','approval')} for p in pages if p['title'] in ('International Futures (IFs)','Understand the Model','Introduction to IFs','Economics')]
    report['code_evidence']={}
    for label,start,end in [('investment_tradeoff',16718,16743),('investment_sector_allocation',12744,12785),
                            ('education_initialization',7845,7867),('education_forecast',14249,14263),('later_investment_adjustments',16916,16938)]:
        view=r.code.read('Models/Economy.Forecast.vb',start,end)
        assert view['local_source_matches_snapshot']
        report['code_evidence'][label]=view
    # Recheck every indexed source, not just cited excerpts; no writes to these inputs.
    report['source_hashes_match']=all(digest((Path(code['root'])/f['path']).read_bytes())==f['sha256'] for f in code['files'])
    assert report['source_hashes_match']
    symbol=r.variable('IGCF',limit=5)
    assert symbol['results_metadata']['Name']=='IGCF' and symbol['code']['total']>0 and symbol['documentation']
    report['variable_catalog']={k:symbol[k] for k in ('requested_symbol','dataset','dictionary_matches','dictionary_input','compatibility','mapping_basis')}
    report['variable_catalog']['result_dimensions']=[{'name':d['column'],'count':len(d['buckets'])} for d in symbol['results_metadata']['dimensions']]
    # Protect the earlier numerical milestone's engine and input provenance.
    baseline=ROOT/'workspace/validation/validation.json'
    if baseline.exists():
        original=json.loads(baseline.read_text(encoding='utf-8'))
        report['numerical_engine_unchanged']=engine_identity()==original['engine']
        assert report['numerical_engine_unchanged']
        report['numerical_inputs_unchanged']=all(fingerprint(p['path'])==p for p in original['inputs_before'])
        assert report['numerical_inputs_unchanged']
    else:report['numerical_baseline']='Not available; run validate_pilot.py for this installation'
    report['research_implementation']={p.name:digest(p.read_bytes()) for p in sorted((ROOT/'src/ifs_research').glob('*.py'))}
    report['status']='passed'
    out=r.config.workspace/'phase3-validation.json'
    out.write_text(json.dumps(report,indent=2,ensure_ascii=True),encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(out),'pages':status['searchable_pages'],'cached_pages':status['pages'],'source_files':len(code['files']),'retrieval_examples':len(cases)}))


if __name__=='__main__':main()
