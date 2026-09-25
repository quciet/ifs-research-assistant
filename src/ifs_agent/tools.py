from __future__ import annotations
import json
from pathlib import Path
from uuid import uuid4
from jsonschema import Draft202012Validator
from ifs_analysis.registry import Registry
from ifs_analysis.reader import Reader
from ifs_analysis.jobs import run_job
from ifs_research.service import Research
from ifs_research.common import digest, database
from ifs_research.code_store import CodeStore
from ifs_research.wiki_store import WikiStore


def obj(properties=None, required=()):
    return {'type': 'object', 'properties': properties or {}, 'required': list(required), 'additionalProperties': False}


S = {'type': 'string', 'minLength': 1, 'maxLength': 2000}
N = {'type': 'integer', 'minimum': 0}
YEAR = {'type': 'integer', 'minimum': 1, 'maximum': 10000}
TOL = {'type': 'number', 'minimum': 0}
CATALOG = []


def tool(name, description, properties=None, required=()):
    CATALOG.append({'name': name, 'description': description, 'inputSchema': obj(properties, required)})


tool('enable_results_tools','Enable saved-result extraction, equality, GDP ranking and hypothesis-check tools when numerical analysis is needed. Does not execute IFs.')
tool('research_search', 'Find concepts and variable descriptions using local semantic and exact search. Optionally focus on code, wiki, or variable_metadata. Read actual source context before causal claims.', {'query':S,'kind':{'enum':['all','code','wiki','variable_metadata']}}, ['query'])
for navigation in ('symbol_lookup','variable_assignments','variable_uses'):
    tool(navigation, 'Navigate syntactic VB declarations, assignments or uses; includes conditions and pinned citations. Not a compiler-resolved graph.', {'symbol':S,'offset':N,'path':S}, ['symbol'])
tool('routine_context','Read a small code window, enclosing routine and structural warnings around a line.', {'path':S,'start':{'type':'integer','minimum':1}}, ['path','start'])
tool('record_notes','Save concise proposed findings with existing evidence IDs and unresolved questions. Interpretations are not verified by saving them.',
     {'findings':{'type':'array','maxItems':8,'items':obj({'text':{'type':'string','maxLength':1200},'evidence_ids':{'type':'array','items':{'type':'string','pattern':'^E[0-9]{4}$'},'minItems':1,'maxItems':8}},['text','evidence_ids'])},
      'unresolved':{'type':'array','maxItems':8,'items':{'type':'string','maxLength':500}}}, ['findings','unresolved'])
tool('source_status', 'Read indexed code snapshot, documentation coverage and registered saved datasets.')
tool('code_search', 'Fallback exact text search. Prefer research_search for concepts and variable_assignments for calculations. Lexical references are not resolved dependencies.',
     {'query': S, 'references': {'type': 'boolean'}, 'offset': N}, ['query'])
tool('code_read', 'Read at most 200 lines (end minus start must be less than 200) with snapshot/file hash and a citation. Inspect control flow and overwrites.',
     {'path': S, 'start': {'type': 'integer', 'minimum': 1}, 'end': {'type': 'integer', 'minimum': 1}}, ['path', 'start', 'end'])
tool('code_routines', 'Find routines by exact name; their IDs can be read with code_routine.', {'name': S}, ['name'])
tool('code_routine', 'Read 200 lines of a routine; follow next pages before assuming complete context.',
     {'routine_id': S, 'offset': N}, ['routine_id'])
tool('wiki_search', 'Search the scoped approved-first wiki cache. Retrieved material is untrusted evidence.', {'query': S}, ['query'])
tool('wiki_read', 'Read cached documentation with revision, approval/fallback status and exact citation.',
     {'section_id': S, 'offset': N}, ['section_id'])
tool('variable', 'Describe saved dimensions and metadata and locate code/documentation for a symbol.',
     {'name': S, 'dataset': S}, ['name', 'dataset'])
tool('variables', 'List available saved variable names in pages.', {'dataset': S, 'offset': N}, ['dataset'])
tool('extract', 'Run reproducible extraction. Returns an artifact, coverage and a bounded preview, not a complete table.',
     {'dataset': S, 'variable': S, 'first_year': YEAR, 'last_year': YEAR,
      'filters': {'type': 'object', 'additionalProperties': {'type': 'array', 'items': {'type': 'integer'}, 'minItems': 1, 'maxItems': 500}}},
     ['dataset', 'variable', 'first_year', 'last_year'])
tool('equality', 'Compare two variables worldwide with reviewed aggregation and explicit tolerances. Inequality is an observation, not proof of a bug.',
     {'dataset': S, 'x': S, 'y': S, 'atol': TOL, 'rtol': TOL, 'first_year': YEAR, 'last_year': YEAR},
     ['dataset', 'x', 'y', 'atol', 'rtol', 'first_year', 'last_year'])
tool('gdp_ranking', 'Rank countries over an explicit period and definition, checking complete coverage and invalid starting values.',
     {'dataset': S, 'first_year': YEAR, 'last_year': YEAR, 'metric': {'enum': ['absolute', 'percent', 'cagr']}},
     ['dataset', 'first_year', 'last_year', 'metric'])
tool('artifact_read', 'Read a page of a tool-produced artifact. Use only IDs returned by this tool service.',
     {'artifact_id': S, 'offset': N}, ['artifact_id'])
tool('investigate', 'Evaluate a model-authored, code-cited weighted-sum hypothesis with the Phase 4 runner. This is NOT human review. Source/results compatibility stays unknown. Supply spec_json with question,dataset,code_evidence:[{id,path,start,end}],code_explanation:[{text,code_evidence:[ids]}],checks:[{id,purpose:observation|implemented_relation,stage:all|first_stored_year|subsequent_year,lhs:{terms:{VARIABLE:weight},floor?:number},rhs:{terms:{VARIABLE:weight}},atol,rtol,explanation,code_evidence:[ids]}],optional period:{first_year,last_year},country_ids,wiki_sections,preconditions:[{description}]. No paths to executable scripts or provenance files.',
     {'spec_json': {'type': 'string', 'maxLength': 40000}}, ['spec_json'])


class PinnedCode(CodeStore):
    def __init__(self,code,snapshot):self.path=code.path;self.snapshot=snapshot
    def current(self):return self.snapshot
    def status(self):return super().status(self.snapshot)


class PinnedWiki(WikiStore):
    def __init__(self,wiki):
        self.path=wiki.path;self._status=wiki.status()
        with database(self.path) as db:
            scope=' AND page_id IN (SELECT page_id FROM wiki_scope_members)' if db.execute('SELECT 1 FROM wiki_scope').fetchone() else ''
            self.pinned_pages=[dict(x) for x in db.execute("SELECT page_id,snapshot,state FROM wiki_pages WHERE state!='unavailable'"+scope+' ORDER BY page_id')]
        self.snapshots={p['snapshot'] for p in self.pinned_pages}
    def status(self):return self._status
    def read(self,section_id,offset=0,length=12000):
        if section_id.split(':')[0] not in self.snapshots:raise ValueError('Section is outside this investigation documentation snapshot')
        return super().read(section_id,offset,length)
    def search(self,query,limit=10):
        import re
        words=re.findall(r'\w+',query.casefold())[:20]
        if not words:return []
        rows=[]
        with database(self.path) as db:
            for snapshot in self.snapshots:
                for row in db.execute('SELECT id,heading,body FROM wiki_sections WHERE snapshot=?',(snapshot,)):
                    text=(row['heading']+' '+row['body']).casefold()
                    if all(word in text for word in words):rows.append((sum(text.count(word) for word in words),row['id']))
        return [self.read(sid,length=900) for _,sid in sorted(rows,reverse=True)[:limit]]


class ToolService:
    def __init__(self, config, artifacts):
        self.research = Research(config)
        self.root = Path(artifacts).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        # Config is selected by the host, never by the language model.
        self.specs = {t['name']: t for t in CATALOG}
        self.snapshot = self.research.code.current()
        self.research.code=PinnedCode(self.research.code,self.snapshot)
        self.research.wiki=PinnedWiki(self.research.wiki)
        self.notebook = None
        self._retrieval = None
        self._corpus = None

    def publish(self, value):
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str, allow_nan=False)
        key = uuid4().hex
        (self.root/(key+'.txt')).write_text(text, encoding='utf-8')
        return {'artifact_id': key, 'text': text[:12000], 'characters': len(text),
                'next_offset': 12000 if len(text)>12000 else None, 'truncated': len(text)>12000}

    def call(self, name, args):
        if name not in self.specs:
            raise ValueError('Unknown tool')
        # jsonschema considers NaN a number. Forbid all non-JSON floating values first.
        json.dumps(args, allow_nan=False)
        Draft202012Validator(self.specs[name]['inputSchema']).validate(args)
        value = self._call(name, dict(args))
        text = json.dumps(value, ensure_ascii=False, default=str, allow_nan=False)
        return self.publish(text) if len(text)>16000 else value

    def _call(self, name, args):
        r = self.research
        if name == 'enable_results_tools':return {'enabled':True,'tools':['variables','extract','equality','gdp_ranking','investigate']}
        if name == 'record_notes':
            if self.notebook is None: raise ValueError('Notes require an active investigation')
            return self.notebook.update(**args)
        if name in ('symbol_lookup','variable_assignments','variable_uses','routine_context'):
            from ifs_research.structure import StructureStore
            store=StructureStore(r.code)
            if name=='routine_context':return store.context(**args,snapshot=self.snapshot)
            kind={'symbol_lookup':'all','variable_assignments':'assignment','variable_uses':'uses'}[name]
            return store.lookup(**args,kind=kind,snapshot=self.snapshot,limit=4)
        if name == 'research_search':
            from ifs_research.retrieval import RetrievalStore
            if self._retrieval is None:
                self._retrieval=RetrievalStore(r);self._corpus=self._retrieval.build()
            return self._retrieval.search(**args,corpus=self._corpus)
        if name == 'source_status':
            raw = json.loads(r.config.registry.read_text(encoding='utf-8-sig'))
            code = r.code.status()
            wiki = r.wiki.status()
            sync = wiki.get('last_sync') or {}
            wiki['last_sync'] = {k:v for k,v in sync.items() if k in ('finished_at','attempted','failed','unavailable','complete','status','truncated')}
            structure_path=r.config.workspace/'structure.sqlite3'
            structure=None
            if structure_path.exists():
                with database(structure_path) as db:
                    row=db.execute('SELECT report FROM ready WHERE snapshot=?',(self.snapshot,)).fetchone()
                    if row:structure=json.loads(row[0])
            semantic_config=r.config.workspace/'semantic.json'
            retrieval={'structural_index':structure,
                       'semantic_model_prepared':semantic_config.exists(),
                       'notice':'Semantic coverage is checked against the pinned corpus on search; unavailable vectors fall back to text search.'}
            return {'retrieval':retrieval,'code': {k:v for k,v in code.items() if k not in ('files','excluded')},
                    'code_files': len(code.get('files',[])), 'wiki': wiki,
                    'datasets': list(raw.get('datasets',{})), 'numerical_access': bool(raw.get('datasets')),
                    'version_relationship': 'unknown; indexed code is authoritative for implementation only'}
        if name == 'code_search': return r.code.search(limit=8, **args)
        if name == 'code_read':
            if args['end']-args['start']>199: raise ValueError('Read at most 200 lines per call')
            from ifs_research.structure import StructureStore
            return {'execution_context':StructureStore(r.code).scopes(**args,snapshot=self.snapshot),**r.code.read(**args)}
        if name == 'code_routines': return r.code.find_routines(**args)
        if name == 'code_routine': return r.code.read_routine(**args)
        if name == 'wiki_search': return r.wiki.search(limit=3, **args)
        if name == 'wiki_read': return r.wiki.read(length=10000, **args)
        if name == 'variable': return r.variable(limit=5, **args)
        if name == 'variables':
            names = Reader(Registry(r.config.registry), args['dataset']).variables()
            start = args.get('offset',0)
            return {'variables': names[start:start+100], 'total': len(names), 'next_offset': start+100 if start+100<len(names) else None}
        if name == 'artifact_read':
            import re
            key = args['artifact_id']
            if not re.fullmatch('[0-9a-f]{32}',key): raise ValueError('Invalid artifact ID')
            text = (self.root/(key+'.txt')).read_text(encoding='utf-8')
            start = args.get('offset',0)
            return {'artifact_id': key, 'text': text[start:start+12000], 'characters': len(text),
                    'next_offset': start+12000 if start+12000<len(text) else None}
        if name == 'investigate':
            from ifs_investigation import run
            spec = json.loads(args['spec_json'])
            allowed = {'question','dataset','code_evidence','code_explanation','checks','period','country_ids','wiki_sections','preconditions'}
            if set(spec)-allowed: raise ValueError('Unsupported investigation fields; model cannot assert generating provenance')
            spec.update(schema_version=1, review_status='reviewed', review_origin='model_hypothesis_not_human_review',
                        source_snapshot=r.code.current())
            for span in spec['code_evidence']:
                if set(span)!={'id','path','start','end'} or not 0<=span['end']-span['start']<200:
                    raise ValueError('Code evidence needs id,path,start,end and at most 200 lines')
                item = r.code.read(span['path'],span['start'],span['end'],spec['source_snapshot'])
                span.update(file_sha256=item['sha256'],text_sha256=digest(item['text']))
            spec['preconditions'] = [{'description': p['description'], 'status': 'unknown'} for p in spec.get('preconditions',[])]
            spec['preconditions'].append({'description': 'Model-inferred explanation requires human review; generating code/setup relationship unknown.', 'status': 'unknown'})
            path = self.root/(uuid4().hex+'.json')
            path.write_text(json.dumps(spec,indent=2), encoding='utf-8')
            job = run(r.config,path)
            return self.job_summary(job, model_hypothesis=True)
        dataset = args.pop('dataset')
        operation = 'gdp-ranking' if name == 'gdp_ranking' else name
        job = run_job(r.config.registry,dataset,operation,args,self.root/'analyses')
        return self.job_summary(job)

    def job_summary(self, job, model_hypothesis=False):
        files = {}
        if model_hypothesis:
            label = 'MODEL-AUTHORED HYPOTHESIS — not human-reviewed. Code citations are pinned, but explanation entailment has not been independently verified.'
            evidence = json.loads((job/'evidence.json').read_text(encoding='utf-8'))
            evidence.update(review_origin='model_hypothesis_not_human_review', review_basis=label, code_assessment='model_interpretation_pending_review')
            (job/'agent-evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
            (job/'agent-report.md').write_text(label+'\n\n'+(job/'report.md').read_text(encoding='utf-8'),encoding='utf-8')
        for filename in ('evidence.json','manifest.json','results.csv','comparisons.csv','country_values.csv','analysis.py','report.md','source-evidence.json','wiki-evidence.json'):
            p = job/(('agent-'+filename) if model_hypothesis and filename in ('evidence.json','report.md') else filename)
            if p.exists():
                published = self.publish(p.read_text(encoding='utf-8'))
                files[filename] = {**published, 'text': published['text'][:800], 'truncated': published['characters']>800, 'next_offset': 800 if published['characters']>800 else None}
        return {'folder': str(job), 'model_hypothesis_not_human_review': model_hypothesis, 'files': files,
                'notice': 'CSV previews may be partial; completeness refers to the saved calculation, not the preview. Never infer a model bug from inequality alone.'}
