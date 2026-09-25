"""Verify the active core wiki graph and report articles separately from section headings."""
import json
from collections import deque
from pathlib import Path
from ifs_research import Research
from ifs_research.common import database,now

ROOT=Path(__file__).resolve().parents[1]


def main():
    research=Research(ROOT/'resources/research.json');wiki=research.wiki;status=wiki.status()
    scope=status['active_scope']
    if not scope:raise ValueError('Run a successful scoped wiki sync first')
    with database(wiki.path) as db:
        report=json.loads(db.execute('SELECT report FROM wiki_syncs WHERE id=?',(scope['run_id'],)).fetchone()[0])
        pages={p['page_id']:p for row in db.execute('SELECT s.payload FROM wiki_pages p JOIN wiki_snapshots s ON s.id=p.snapshot JOIN wiki_scope_members m ON m.page_id=p.page_id') for p in [json.loads(row[0])]}
        aliases={row[0]:row[1] for row in db.execute('SELECT alias,page_id FROM wiki_aliases')}
        cached=[row[0] for row in db.execute('SELECT title FROM wiki_pages WHERE page_id NOT IN (SELECT page_id FROM wiki_scope_members) ORDER BY title')]
    unavailable={x['title'] for x in report['skipped'] if x['reason']=='missing or non-article'}
    queue=deque(scope['roots']);seen=set();unresolved=set()
    while queue:
        title=queue.popleft();pid=aliases.get(title)
        if pid not in pages:
            if title not in unavailable:unresolved.add(title)
            continue
        if pid in seen:continue
        seen.add(pid)
        queue.extend(link['title'] for link in pages[pid]['content'].get('links',[]) if link.get('ns')==0)
    assert not unresolved, f'Unaccounted-for links: {unresolved}'
    assert seen==set(pages), 'Active scope is not exactly the reachable article graph'
    assert report['status']=='complete_for_scope' and not report['pending'] and not report['failed']
    rows=[{key:entry[key] for key in ('title','revision','approval_status','headings','sections','depth','parent')} for entry in report['imported']]
    result={'checked_at':now(),'roots':scope['roots'],'status':'all_retrievable_linked_articles_accounted_for',
            'articles':len(pages),'wiki_section_headings':sum(x['headings'] for x in rows),
            'searchable_passages':status['active_sections'],'approval_counts':status['approval_counts'],
            'pages':rows,'unavailable_links':report['skipped'],'pending':report['pending'],
            'excluded_cached_titles':cached,
            'limitations':['Scope follows main-namespace article links from the selected approved-first revisions.',
                'Article completeness does not include OCR, external documents, or verification of embedded template/image approval.',
                'Heading counts and searchable passage counts differ: long sections split, empty headings can group child sections.']}
    live_path=research.config.workspace/'core-wiki-live-audit.json'
    if live_path.exists():
        live=json.loads(live_path.read_text(encoding='utf-8'))
        result['site_statistics']=live['site_statistics']['query']['statistics']
        result['main_namespace_title_count']=len(live['main_namespace_titles'])
        result['additional_literal_subpages']=[p['title'] for p in live['main_namespace_titles'] if any(p['title'].startswith(x['title']+'/') for x in rows)]
        assert not result['additional_literal_subpages'],'Review literal subpages outside linked graph'
    target=research.config.workspace/'core-wiki-coverage.json'
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(target),'articles':result['articles'],'headings':result['wiki_section_headings'],'passages':result['searchable_passages'],'unavailable_links':len(unavailable),'excluded_cached_articles':len(cached)}))


if __name__=='__main__':main()
