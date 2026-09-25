from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .registry import Registry, fingerprint, readonly
from .reader import Reader
from .jobs import run_job, write_json
from .errors import AnalysisError


def inventory(registry):
    result = {'source_label': registry.config.get('source_label'), 'datasets': [],
              'country_members': registry.countries(), 'references': {},
              'limitations': ['Run databases do not establish generating commit, scenario settings, or dollar base year.']}
    for key in ('code_source', 'variable_dictionary'):
        if registry.config.get(key):
            path = registry.resolve(registry.config[key])
            result['references'][key] = {'path': str(path), 'exists': path.exists()}
    result['references']['documentation'] = [{'path': str(registry.resolve(p)), 'exists': registry.resolve(p).exists()}
                                             for p in registry.config.get('documentation', [])]
    for item in registry.list_datasets():
        reader = Reader(registry, item['id'])
        with readonly(reader.path) as db:
            schema = {r[0]: [dict(c) for c in db.execute('PRAGMA table_info("'+r[0].replace('"','""')+'")')]
                      for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
            dims = [dict(r) for r in db.execute('SELECT d.Id,d.Name,count(b.Seq) AS buckets,min(b.Seq) AS first_key,max(b.Seq) AS last_key '
                                              'FROM ifs_dim d LEFT JOIN ifs_dim_bucket b ON d.Id=b.DimensionId GROUP BY d.Id ORDER BY d.Id')]
        result['datasets'].append({**item, 'fingerprints': [fingerprint(p) for p in registry.input_paths(item['id'])],
                                   'years': reader.years(), 'variable_count': len(reader.variables()),
                                   'schema': schema, 'dimensions': dims,
                                   'pilot_metadata': [reader.describe(v) for v in registry.config['variable_semantics']]})
    return result


def parser():
    p = argparse.ArgumentParser(description='Read-only IFs saved-results analysis')
    p.add_argument('--registry', type=Path, required=True)
    p.add_argument('--output', type=Path, default=Path('workspace/jobs'))
    commands = p.add_subparsers(dest='command', required=True)
    commands.add_parser('datasets')
    commands.add_parser('inventory')
    for name in ('variables', 'describe', 'extract', 'equality', 'gdp-ranking', 'reconciliation'):
        sub = commands.add_parser(name)
        sub.add_argument('--dataset', required=True)
        if name in ('describe','extract'):
            sub.add_argument('--variable', required=True)
        if name in ('extract','equality','gdp-ranking'):
            sub.add_argument('--first-year', type=int, required=name=='gdp-ranking')
            sub.add_argument('--last-year', type=int, required=name=='gdp-ranking')
        if name == 'extract':
            sub.add_argument('--filter', action='append', default=[], help='dimension=ID,ID (country_id or dim_N)')
        if name == 'equality':
            sub.add_argument('--x', required=True); sub.add_argument('--y', required=True)
            sub.add_argument('--atol', type=float, required=True); sub.add_argument('--rtol', type=float, required=True)
        if name == 'gdp-ranking':
            sub.add_argument('--metric', choices=['absolute','percent','cagr'], required=True)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        registry = Registry(args.registry)
        if args.command == 'datasets':
            print(json.dumps(registry.list_datasets(), indent=2)); return 0
        if args.command == 'inventory':
            # Inventory artifacts use the same source/output separation policy as analysis commands.
            root = registry.validate_output(args.output)
            payload = inventory(registry)
            root.mkdir(parents=True, exist_ok=True)
            write_json(root/'inventory.json', payload)
            print(root/'inventory.json'); return 0
        if args.command in ('variables','describe'):
            reader = Reader(registry, args.dataset)
            result = reader.variables() if args.command == 'variables' else reader.describe(args.variable)
            print(json.dumps(result, indent=2)); return 0
        params = {}
        if args.command in ('extract','equality','gdp-ranking'):
            params.update(first_year=args.first_year, last_year=args.last_year)
        if args.command == 'extract':
            filters = {}
            for term in args.filter:
                name, values = term.split('=',1)
                if name in filters: raise AnalysisError('Duplicate dimension filter')
                filters[name] = [int(v) for v in values.split(',')]
            params.update(variable=args.variable, filters=filters)
        if args.command == 'equality':
            params.update(x=args.x, y=args.y, atol=args.atol, rtol=args.rtol)
        if args.command == 'gdp-ranking': params['metric'] = args.metric
        job = run_job(args.registry, args.dataset, args.command, params, args.output)
        print(job)
        return 0
    except (AnalysisError, OSError, ValueError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
