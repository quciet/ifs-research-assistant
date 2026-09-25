from __future__ import annotations
import argparse
import json
import sqlite3
import sys
from ifs_analysis.errors import AnalysisError
from .common import Config, ResearchError
from .service import Research
from .wiki_client import WikiClient, Transport


def parser():
    p = argparse.ArgumentParser(description='Local IFs code and revision-aware wiki investigation')
    p.add_argument('--config', default='resources/research.json')
    sub = p.add_subparsers(dest='command', required=True)
    sync = sub.add_parser('wiki-sync', help='Explicit network refresh; bounded public read-only requests')
    sync.add_argument('--max-pages', type=int)
    sync.add_argument('--max-depth', type=int)
    sync.add_argument('--seed', action='append', help='Override configured seeds; can repeat')
    sub.add_parser('wiki-status')
    s = sub.add_parser('wiki-search'); s.add_argument('query'); s.add_argument('--limit', type=int, default=10)
    s = sub.add_parser('wiki-read'); s.add_argument('section_id'); s.add_argument('--offset', type=int, default=0); s.add_argument('--length', type=int, default=12000)
    s = sub.add_parser('wiki-source'); s.add_argument('snapshot'); s.add_argument('--format', choices=['wikitext','html'], default='wikitext'); s.add_argument('--offset', type=int, default=0); s.add_argument('--length', type=int, default=12000)
    sub.add_parser('code-index')
    sub.add_parser('code-status')
    for name in ('code-search', 'code-references'):
        s = sub.add_parser(name); s.add_argument('query'); s.add_argument('--limit', type=int, default=20); s.add_argument('--offset', type=int, default=0); s.add_argument('--snapshot')
        if name=='code-search':s.add_argument('--literal', action='store_true', help='Case-sensitive exact text, including punctuation')
    s = sub.add_parser('code-read'); s.add_argument('path'); s.add_argument('--start', type=int, default=1); s.add_argument('--end', type=int); s.add_argument('--snapshot')
    s = sub.add_parser('code-find-routine'); s.add_argument('name')
    s = sub.add_parser('code-routine'); s.add_argument('routine_id'); s.add_argument('--offset', type=int, default=0)
    s = sub.add_parser('variable'); s.add_argument('name'); s.add_argument('--dataset', default='IFsBase'); s.add_argument('--limit', type=int, default=10)
    s=sub.add_parser('investigation-start');s.add_argument('--question',required=True);s.add_argument('--variables',nargs='+',required=True);s.add_argument('--dataset',required=True)
    s=sub.add_parser('investigation-run');s.add_argument('spec')
    s=sub.add_parser('investigation-replay');s.add_argument('folder')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        c = Config(args.config); r = Research(c); command = args.command
        if command == 'investigation-start':
            from ifs_investigation import draft
            result={'folder':str(draft(c,args.question,args.variables,args.dataset)),'status':'source_review_required'}
        elif command == 'investigation-run':
            from ifs_investigation import run
            result={'folder':str(run(c,args.spec))}
        elif command == 'investigation-replay':
            from ifs_investigation import replay
            result={'folder':str(replay(args.folder))}
        elif command == 'wiki-sync':
            w = c.data['wiki']
            result = r.wiki.sync(WikiClient(Transport(w['api'])), args.seed or w['seeds'],
                                max_pages=args.max_pages if args.max_pages is not None else w.get('max_pages', 200),
                                max_depth=args.max_depth if args.max_depth is not None else w.get('max_depth', 3),
                                scoped=w.get('scoped',False),
                                progress=lambda x: print(json.dumps(x), file=sys.stderr, flush=True))
            (c.workspace / 'wiki-sync-report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        elif command == 'wiki-status': result = r.wiki.status()
        elif command == 'wiki-search': result = r.wiki.search(args.query, args.limit)
        elif command == 'wiki-read': result = r.wiki.read(args.section_id, args.offset, args.length)
        elif command == 'wiki-source': result = r.wiki.source(args.snapshot, args.format, args.offset, args.length)
        elif command == 'code-index': result = r.code.index(c.code_root)
        elif command == 'code-status': result = r.code.status()
        elif command in ('code-search', 'code-references'): result = r.code.search(args.query, args.limit, args.offset, args.snapshot, command == 'code-references', literal=getattr(args,'literal',False))
        elif command == 'code-read': result = r.code.read(args.path, args.start, args.end, args.snapshot)
        elif command == 'code-find-routine': result = r.code.find_routines(args.name)
        elif command == 'code-routine': result = r.code.read_routine(args.routine_id, args.offset)
        else: result = r.variable(args.name, args.dataset, args.limit)
        print(json.dumps(result, indent=2, ensure_ascii=True, default=str))
        return 0
    except (ResearchError, AnalysisError, OSError, sqlite3.Error, KeyError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('Cancelled; completed wiki pages and sync checkpoint remain available.', file=sys.stderr)
        return 130
