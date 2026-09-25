from __future__ import annotations
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .errors import AnalysisError


def fingerprint(path):
    path = Path(path).resolve()
    before = path.stat()
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise AnalysisError(f'Source changed while fingerprinting: {path}')
    return {'path': str(path), 'sha256': h.hexdigest(), 'bytes': after.st_size}


@contextmanager
def readonly(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise AnalysisError(f'Source does not exist: {path}')
    # Immutable avoids SQLite sidecars. Reject live WAL/journal files: only stable saved snapshots qualify.
    if any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-journal')):
        raise AnalysisError(f'Live SQLite sidecar present; supply a closed snapshot: {path}')
    conn = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    try:
        yield conn
    finally:
        conn.close()


class Registry:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.config = json.loads(self.path.read_text(encoding='utf-8-sig'))
        if self.config.get('schema_version') != 1 or not self.config.get('datasets'):
            raise AnalysisError('Registry requires schema_version=1 and datasets')

    def resolve(self, path):
        return (self.path.parent / path).resolve()

    def dataset(self, dataset_id):
        try:
            item = dict(self.config['datasets'][dataset_id])
        except KeyError as exc:
            raise AnalysisError(f'Unknown dataset: {dataset_id}') from exc
        item['id'] = dataset_id
        item['path'] = self.resolve(item['path'])
        return item

    def list_datasets(self):
        return [{**self.dataset(key), 'path': str(self.dataset(key)['path'])}
                for key in self.config['datasets']]

    def input_paths(self, dataset_id):
        item = self.dataset(dataset_id)
        paths = [self.path, item['path']]
        for key in ('variable_dictionary', 'country_membership'):
            if self.config.get(key):
                paths.append(self.resolve(self.config[key]))
        if item.get('scenario_file'):
            paths.append(self.resolve(item['scenario_file']))
        return paths

    def countries(self):
        membership = json.loads(self.resolve(self.config['country_membership']).read_text(encoding='utf-8-sig'))
        rows = membership['members']
        ids = [int(r['id']) for r in rows]
        names = [r['name'] for r in rows]
        if not rows or len(ids) != len(set(ids)) or len(names) != len(set(names)):
            raise AnalysisError('Country membership must be nonempty with unique IDs and names')
        if any(r.get('kind') != 'country_or_territory' for r in rows):
            raise AnalysisError('Membership contains non-country aggregate entries')
        return {int(r['id']): r['name'] for r in rows}

    def validate_output(self, output):
        output = Path(output).resolve()
        protected = [self.resolve(p) for p in self.config.get('protected_roots', [])]
        protected += [self.dataset(k)['path'].parent for k in self.config['datasets']]
        if self.config.get('code_source'):
            protected.append(self.resolve(self.config['code_source']))
        if self.config.get('variable_dictionary'):
            protected.append(self.resolve(self.config['variable_dictionary']).parent)
        protected += [self.resolve(p).parent for p in self.config.get('documentation', [])]
        if any(output == p or p in output.parents for p in protected):
            raise AnalysisError('Output folder overlaps a read-only source location')
        return output
