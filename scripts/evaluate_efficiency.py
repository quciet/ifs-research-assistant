"""Offline retrieval ablation and saved-run accounting. Never calls an LLM API.

Run with .venv/Scripts/python scripts/evaluate_efficiency.py.
Output is a diagnostic, not an automated correctness judgment of causal answers.
"""
import argparse
import json
from pathlib import Path
import time
from ifs_research.service import Research
from ifs_research.structure import StructureStore
from ifs_research.retrieval import RetrievalStore


def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser();parser.add_argument('--config',default=str(root/'resources/research.json'))
    parser.add_argument('--output',default=str(root/'workspace/efficiency-evaluation/report.json'))
    args=parser.parse_args();r=Research(args.config);index=StructureStore(r.code);retrieval=RetrievalStore(r)
    cases=json.loads((root/'resources/efficiency-cases.json').read_text(encoding='utf-8'))['cases']
    report={'kind':'offline_retrieval_ablation','source_snapshot':r.code.current(),'cases':[],
            'notice':'Path/kind hits measure navigation only, not answer quality or causal correctness. Legacy lexical uses fixed queries, not adaptive query rewriting by the old agent. Text and hybrid share chunks; structural receives known symbols. No live requests or token savings are inferred.'}
    for case in cases:
        if 'query' not in case:continue
        row={'id':case['id'],'query':case['query'],'configurations':{}}
        for mode in ('legacy_lexical','text','structural','hybrid'):
            start=time.monotonic();hits=[]
            if mode=='legacy_lexical':
                hits=[{'kind':'code',**x} for x in r.code.search(case['query'],limit=6)['hits']]
                hits.extend({'kind':'wiki',**x} for x in r.wiki.search(case['query'],limit=3))
            elif mode=='structural':
                # Symbols are reviewed navigation targets, not inferred by this benchmark.
                for symbol in case.get('symbols',[]):hits.extend({'kind':'code',**x} for x in index.lookup(symbol,kind='assignment',limit=6)['hits'])
            else:
                result=retrieval.search(case['query'],semantic=mode=='hybrid');hits=result['hits']
                if mode=='hybrid':row['semantic_status']=result['semantic_status']
            paths={x.get('path') or (x.get('citation',{}).get('path') if isinstance(x.get('citation'),dict) else None) for x in hits}
            row['configurations'][mode]={'elapsed_seconds':round(time.monotonic()-start,3),'returned_characters':len(json.dumps(hits)),
                'target_paths_found':sorted(paths & set(case.get('expected_paths',[]))),
                'expected_kind_found':any(x.get('kind')==case.get('expected_kind') for x in hits) if case.get('expected_kind') else None,
                'hits':[{'kind':x.get('kind'),'citation':x.get('citation'),'label':x.get('label')} for x in hits]}
        report['cases'].append(row)
    logs=[]
    for path in sorted((root/'workspace/agent/conversations').glob('*.jsonl')):
        try:events=[json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()]
        except (ValueError,OSError):continue
        summaries=[x['summary'] for x in events if x['type']=='usage_summary']
        outcome=next((x.get('outcome',x.get('status')) for x in reversed(events) if x['type']=='done'),'unfinished')
        logs.append({'run':path.name,'outcome':outcome,'usage':summaries[-1] if summaries else None,
                     'logged_tool_starts':sum(e['type']=='tool_start' for e in events),
                     'notice':'Older runs may lack token/stage accounting; do not treat missing data as zero.'})
    report['saved_runs']=logs
    dest=Path(args.output).resolve()
    if not dest.is_relative_to(root/'workspace'):raise ValueError('Write evaluation artifacts inside the project workspace')
    dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(dest)


if __name__=='__main__':main()
