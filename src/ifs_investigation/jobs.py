from __future__ import annotations
import json
import shutil
import sys
from pathlib import Path
from uuid import uuid4
from datetime import datetime,timezone
from ifs_analysis import Registry,Reader
from ifs_analysis.errors import AnalysisError
from ifs_analysis.registry import fingerprint
from ifs_analysis.jobs import engine_identity
from ifs_research import Research
from ifs_research.common import ResearchError,digest
from .engine import evaluate,validate


def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=True,allow_nan=False,default=str),encoding='utf-8')


def implementation():
    base=Path(__file__).resolve().parents[1]
    return {'numerical':engine_identity(),'research':{p.name:digest(p.read_bytes()) for p in sorted((base/'ifs_research').glob('*.py'))},
            'investigation':{p.name:digest(p.read_bytes()) for p in sorted(Path(__file__).parent.glob('*.py'))}}


def compatibility(spec,registry,dataset,snapshot):
    evidence=spec.get('version_evidence')
    if not evidence:return 'unknown',None
    if not Path(evidence).is_absolute():raise ResearchError('Version evidence must use an absolute path')
    path=Path(evidence).resolve()
    provenance=json.loads(path.read_text(encoding='utf-8-sig'))
    if not provenance.get('basis') or not provenance.get('source_snapshot') or not provenance.get('dataset_sha256'):
        raise ResearchError('Version evidence must bind a dataset SHA-256 to a source snapshot and explain its basis')
    match=provenance['source_snapshot']==snapshot and provenance['dataset_sha256']==fingerprint(registry.dataset(dataset)['path'])['sha256']
    return ('documented_match' if match else 'documented_mismatch'),{'input':fingerprint(path),'statement':provenance,
        'notice':'Documented provenance supplied to the investigation, not inferred from numerical agreement.'}


def draft(config,question,variables,dataset):
    research=Research(config);code=research.code.status()
    if not code['indexed']:raise ResearchError('Index the supplied code first')
    folder=research.config.workspace/'investigations'/('draft-'+uuid4().hex[:10]);folder.mkdir(parents=True)
    evidence={}
    for variable in variables:
        # Full paginated inventory: a short first page must not hide later overwrites.
        result=research.code.search(variable,references=True,limit=100);hits=list(result['hits'])
        while result['next_offset'] is not None:
            result=research.code.search(variable,references=True,limit=100,offset=result['next_offset']);hits.extend(result['hits'])
        evidence[variable]={'references':hits,'reference_count':len(hits),'wiki_candidates':research.wiki.search(variable,3)}
    write(folder/'discovery.json',evidence)
    write(folder/'investigation.json',{'schema_version':1,'question':question,'user_expectation':None,'dataset':dataset,
        'source_snapshot':code['snapshot'],'review_status':'draft','code_evidence':[],'wiki_sections':[],
        'code_explanation':[],'preconditions':[],'checks':[],
        'review_instructions':'Trace actual assignments, initialization, call order, bounds, and overrides. Name matches are not bindings. Attach reviewed code snippets and supported checks; do not assume the user expectation is a requirement.'})
    return folder


def report_markdown(evidence,sources,docs):
    out=['# '+evidence['question'],'', '**Implementation explanation:** reviewed against the supplied source snapshot.', '',
         '**Saved-run attribution:** '+evidence['outcome']+'. Numerical agreement does not establish generating provenance.', '',
         'The supplied code controls the explanation. Numerical consistency is conditional on source/results provenance and the recorded preconditions.', '', '## Implemented behavior','']
    for claim in evidence.get('code_explanation',[]):
        out.append('- '+claim['text']+' ['+', '.join(claim['code_evidence'])+']')
    out+=['','## Saved-result checks','', 'Value units: '+evidence.get('value_units','unavailable')+'. Currency base year remains governed by the dataset metadata.','']
    for c in evidence.get('checks',[]):
        word='observations' if c['purpose']=='observation' else 'comparisons'
        out.append(f"- {c['id']}: {c['outside_tolerance']} of {c['rows']} country/year {word} outside tolerance; maximum absolute difference {c['max_absolute_difference']}. {c['interpretation']}")
    if evidence.get('numeric_error'):out+=['', 'Numerical evidence unavailable: '+evidence['numeric_error']]
    out+=['','## Conditions and provenance','', 'Code/results relationship: **'+evidence['compatibility']+'**.']
    for p in evidence.get('preconditions',[]):out.append('- '+p['description']+' — '+p['status']+'. '+p.get('evidence',''))
    out+=['','First stored year is not automatically proven to be the initialization year. A discrepancy is not a model-bug verdict. When numerical extraction succeeds, country_values.csv and comparisons.csv retain complete observations and both country and aggregate comparisons.','', '## Code citations','']
    for item in sources:out.append(f"- {item['id']}: {item['path']}, snapshot lines {item['start']}–{item['end']}; file SHA-256 {item['sha256']}. Exact text is archived in source-evidence.json.")
    out+=['','## Supporting documentation','']
    for doc in docs:out.append(f"- [{doc['title']} — {doc['heading']}]({doc['citation']}): {doc['selection']}; approval {doc['approval']['status']}. Wiki/code compatibility is unverified; embedded and extraction limitations remain in wiki-evidence.json.")
    return '\n'.join(out)+'\n'


def run(config,spec_path,expected=None):
    research=Research(config);spec_path=Path(spec_path).resolve()
    spec=json.loads(spec_path.read_text(encoding='utf-8-sig'));validate(spec)
    registry=Registry(research.config.registry);dataset=spec['dataset']
    root=registry.validate_output(research.config.workspace/'investigations')
    job=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex[:8]);job.mkdir(parents=True)
    manifest={'status':'running','config':str(research.config.path),'original_spec':str(spec_path),'dataset':dataset}
    write(job/'investigation.json',spec)
    try:
        code=research.code.status()
        if code['snapshot']!=spec['source_snapshot']:raise ResearchError('Source review required: selected code snapshot differs from the reviewed investigation')
        base=Path(code['root'])
        source_paths=[base/x['path'] for x in code['files']]
        if any(fingerprint(base/x['path'])['sha256']!=x['sha256'] for x in code['files']):raise ResearchError('Source review required: local code differs from indexed snapshot; reindex and review')
        inputs=[research.config.path,*registry.input_paths(dataset),*source_paths]
        if spec.get('version_evidence'):inputs.append(Path(spec['version_evidence']).resolve())
        inputs=list(dict.fromkeys(inputs));before=[fingerprint(p) for p in inputs];engine=implementation()
        if expected and (before!=expected['inputs'] or engine!=expected['engine'] or digest(json.dumps(spec,sort_keys=True))!=expected['spec_sha256']):
            raise ResearchError('Replay inputs, review specification, or implementation changed')
        manifest.update(inputs=before,engine=engine,spec_sha256=digest(json.dumps(spec,sort_keys=True)),source_snapshot=code['snapshot'])
        sources=[]
        for e in spec['code_evidence']:
            item=research.code.read(e['path'],e['start'],e['end'],spec['source_snapshot'])
            if item['sha256']!=e['file_sha256'] or digest(item['text'])!=e['text_sha256']:raise ResearchError('Reviewed code citation changed or is incorrectly bound')
            sources.append({'id':e['id'],**item})
        docs=[research.wiki.read(sid) for sid in spec.get('wiki_sections',[])]
        write(job/'source-evidence.json',sources);write(job/'wiki-evidence.json',docs);write(job/'source-manifest.json',code)
        relation,version=compatibility(spec,registry,dataset,code['snapshot'])
        selected=registry.dataset(dataset)
        scenario={k:str(v) if isinstance(v,Path) else v for k,v in selected.items() if k in ('scenario_identity','scenario_file','scenario_relationship','generating_version')}
        try:
            values,comparisons,evidence=evaluate(Reader(registry,dataset),spec,relation)
            values.to_csv(job/'country_values.csv',index=False,float_format='%.17g')
            comparisons.to_csv(job/'comparisons.csv',index=False,float_format='%.17g')
            manifest['tables']={name:fingerprint(job/name)['sha256'] for name in ('country_values.csv','comparisons.csv')}
        except (AnalysisError,ResearchError) as exc:
            evidence={'question':spec['question'],'code_explanation':spec.get('code_explanation',[]),'checks':[],
                'outcome':'incompatible_inputs' if relation=='documented_mismatch' else 'insufficient_evidence',
                'compatibility':relation,'preconditions':spec.get('preconditions',[]),'numeric_error':str(exc),
                'code_assessment':'reviewed_supplied_implementation','numeric_consistency':'unavailable'}
            manifest['tables']={}
        evidence.update(version_evidence=version,scenario= scenario,code_snapshot=code['snapshot'],
                        review_basis='Explicit reviewed investigation specification; this runner does not infer arbitrary code semantics.')
        if [fingerprint(p) for p in inputs]!=before or implementation()!=engine:raise ResearchError('Inputs or implementation changed during investigation')
        if expected and (manifest['tables']!=expected['tables'] or evidence['outcome']!=expected['outcome']):raise ResearchError('Replayed output differs')
        write(job/'evidence.json',evidence)
        (job/'report.md').write_text(report_markdown(evidence,sources,docs),encoding='utf-8')
        (job/'analysis.py').write_text('from pathlib import Path\nfrom ifs_investigation import replay\nprint(replay(Path(__file__).resolve().parent))\n',encoding='utf-8')
        package_root=Path(__file__).resolve().parents[1]
        for name in ('ifs_investigation','ifs_research','ifs_analysis'):
            target=job/'implementation'/name;target.mkdir(parents=True)
            for file in (package_root/name).glob('*.py'):shutil.copyfile(file,target/file.name)
        manifest.update(status='complete_with_numeric_limit' if evidence.get('numeric_error') else 'complete',outcome=evidence['outcome'])
        (job/'execution.log').write_text('Code evidence bound to reviewed snapshot before calculation.\nRead-only saved-result calculation '+('unavailable' if evidence.get('numeric_error') else 'completed')+'.\nSource/input fingerprints unchanged.\nOutcome: '+evidence['outcome']+'\n'+(evidence.get('numeric_error') or '')+'\n',encoding='utf-8')
    except Exception as exc:
        manifest.update(status='failed',error=str(exc))
        (job/'execution.log').write_text(str(exc)+'\n',encoding='utf-8')
        raise
    finally:write(job/'manifest.json',manifest)
    return job


def replay(folder):
    folder=Path(folder).resolve();m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if m['status'] not in ('complete','complete_with_numeric_limit'):raise ResearchError('Only completed investigations can be replayed')
    return run(m['config'],folder/'investigation.json',expected=m)
