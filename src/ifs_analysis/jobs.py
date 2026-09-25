from __future__ import annotations
import importlib.metadata
import json
import platform
import traceback
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import numpy as np
from . import __version__
from .registry import Registry, fingerprint
from .reader import Reader
from .analysis import check_equality, rank_gdp, reconcile_investment
from .errors import AnalysisError


def write_json(path, value):
    def encode(v):
        if isinstance(v, Path): return str(v)
        if isinstance(v, np.generic): return v.item()
        raise TypeError(f'Cannot serialize {type(v)}')
    Path(path).write_text(json.dumps(value, indent=2, default=encode, allow_nan=False), encoding='utf-8')


def engine_identity():
    package = Path(__file__).parent
    return {'version': __version__, 'python': platform.python_version(),
            'dependencies': {name: importlib.metadata.version(name) for name in ('numpy', 'pandas', 'fastparquet', 'cramjam', 'fsspec', 'packaging', 'python-dateutil', 'six', 'tzdata')},
            'files': {p.name: fingerprint(p)['sha256'] for p in sorted(package.glob('*.py'))}}


def run_job(registry_path, dataset_id, operation, parameters, output_root, expected_inputs=None, expected_engine=None):
    registry = Registry(registry_path)
    output_root = registry.validate_output(output_root)
    job = output_root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid4().hex[:8])
    job.mkdir(parents=True)
    manifest = {'status': 'running', 'dataset_id': dataset_id, 'operation': operation, 'parameters': parameters,
                'registry': str(registry.path), 'started_utc': datetime.now(timezone.utc).isoformat(),
                'limitations': ['Generating code version is not verified.',
                               'Dictionary currency base year is not verified against saved results.',
                               'Nearby scenario files are not proven generating setup.']}
    try:
        inputs = [fingerprint(p) for p in registry.input_paths(dataset_id)]
        engine = engine_identity()
        if expected_inputs is not None and inputs != expected_inputs:
            raise AnalysisError('Replay inputs differ from original fingerprints')
        if expected_engine is not None and engine != expected_engine:
            raise AnalysisError('Replay package or Python/dependency versions differ')
        manifest.update(inputs=inputs, engine=engine)
        archive = job / 'implementation'
        archive.mkdir()
        for source in Path(__file__).parent.glob('*.py'):
            (archive / source.name).write_bytes(source.read_bytes())
        reader = Reader(registry, dataset_id)
        if operation == 'equality':
            table, evidence = check_equality(reader, **parameters)
        elif operation == 'gdp-ranking':
            table, evidence = rank_gdp(reader, **parameters)
        elif operation == 'reconciliation':
            table, evidence = reconcile_investment(reader)
        elif operation == 'extract':
            selection = reader.extract(**parameters)
            table, evidence = selection.table, {'metadata': selection.metadata, 'coverage': selection.coverage}
        else:
            raise AnalysisError(f'Unknown operation: {operation}')
        if [fingerprint(p) for p in registry.input_paths(dataset_id)] != inputs:
            raise AnalysisError('Input changed during execution; result rejected')
        if engine_identity() != engine:
            raise AnalysisError('Analysis code changed during execution')
        table.to_csv(job / 'results.csv', index=False, float_format='%.17g')
        write_json(job / 'evidence.json', evidence)
        manifest.update(status='complete', output_rows=len(table), output_sha256=fingerprint(job/'results.csv')['sha256'])
        script = '''# Reproduce this analysis with the same installed package and registered sources.
from pathlib import Path
import json
from ifs_analysis.jobs import run_job
here = Path(__file__).resolve().parent
m = json.loads((here / 'manifest.json').read_text(encoding='utf-8'))
job = run_job(m['registry'], m['dataset_id'], m['operation'], m['parameters'],
              here.parent, expected_inputs=m['inputs'], expected_engine=m['engine'])
new = json.loads((job / 'manifest.json').read_text(encoding='utf-8'))
assert new['output_sha256'] == m['output_sha256'], 'Replayed output differs'
print(job)
'''
        (job / 'analysis.py').write_text(script, encoding='utf-8')
        (job / 'execution.log').write_text('Completed deterministic analysis. Source fingerprints unchanged.\n'
                                        + f'Operation: {operation}\nRows: {len(table)}\n', encoding='utf-8')
    except Exception as exc:
        manifest.update(status='failed', error=str(exc))
        (job / 'execution.log').write_text(traceback.format_exc(), encoding='utf-8')
        raise
    finally:
        manifest['finished_utc'] = datetime.now(timezone.utc).isoformat()
        write_json(job / 'manifest.json', manifest)
    return job
