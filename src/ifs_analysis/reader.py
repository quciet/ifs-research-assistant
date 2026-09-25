from __future__ import annotations
from dataclasses import dataclass
from math import prod
import io
import numpy as np
import pandas as pd
from fastparquet import ParquetFile
from .decoder import decode
from .errors import AnalysisError
from .registry import readonly


@dataclass
class Selection:
    table: pd.DataFrame
    metadata: dict
    coverage: dict

    def require_complete(self):
        if not self.coverage['complete']:
            raise AnalysisError(f'Incomplete selection: {self.coverage}')
        return self


class Reader:
    def __init__(self, registry, dataset_id):
        self.registry = registry
        self.dataset = registry.dataset(dataset_id)
        self.path = self.dataset['path']
        self.stat = self._stat()
        self._cache = {}

    def _stat(self):
        s = self.path.stat()
        return s.st_size, s.st_mtime_ns

    def assert_unchanged(self):
        if self.stat != self._stat():
            raise AnalysisError('Results changed during this reader session; reopen a stable snapshot')

    def variables(self):
        self.assert_unchanged()
        with readonly(self.path) as db:
            return [r[0] for r in db.execute('SELECT Name FROM ifs_var ORDER BY Name')]

    def describe(self, variable):
        self.assert_unchanged()
        with readonly(self.path) as db:
            row = db.execute('SELECT * FROM ifs_var WHERE Name=?', (variable,)).fetchone()
            if row is None:
                raise AnalysisError(f'Unknown variable: {variable}')
            meta = dict(row)
            dimensions = []
            for dim in db.execute('SELECT vd.Seq, d.Id, d.Name FROM ifs_var_dim vd '
                                  'JOIN ifs_dim d ON d.Id=vd.DimensionId '
                                  'WHERE vd.VariableName=? ORDER BY vd.Seq', (variable,)):
                buckets = {int(r[0]): r[1] for r in db.execute(
                    'SELECT Seq, Name FROM ifs_dim_bucket WHERE DimensionId=? ORDER BY Seq', (dim['Id'],))}
                dimensions.append({'id': dim['Id'], 'source_name': dim['Name'],
                                   'column': {0: 'year', 1: 'country_id'}.get(dim['Id'], f"dim_{dim['Id']}"),
                                   'buckets': buckets})
            if not dimensions or len({d['id'] for d in dimensions}) != len(dimensions):
                raise AnalysisError('Missing or repeated dimension definitions are unsupported')
            meta['dimensions'] = dimensions
        meta['dictionary'] = None
        dictionary = self.registry.config.get('variable_dictionary')
        if dictionary:
            with readonly(self.registry.resolve(dictionary)) as db:
                row = db.execute('SELECT NAME, DEFINITION, UNITS, "DISPLAY UNITS", CURRENCY, AGGREGATION '
                                 'FROM IFSVAR WHERE NAME=?', (variable,)).fetchone()
                if row:
                    meta['dictionary'] = dict(row)
        meta['dataset_id'] = self.dataset['id']
        meta['generating_version'] = self.dataset.get('generating_version')
        meta['dictionary_version_match'] = 'unverified'
        meta['semantics'] = self.registry.config.get('variable_semantics', {}).get(variable)
        return meta

    def years(self):
        with readonly(self.path) as db:
            years = [r[0] for r in db.execute('SELECT Seq FROM ifs_dim_bucket WHERE DimensionId=0 ORDER BY Seq')]
        if not years or years != list(range(min(years), max(years) + 1)):
            raise AnalysisError('Time catalog is empty or has gaps')
        return years

    def extract(self, variable, first_year=None, last_year=None, filters=None):
        self.assert_unchanged()
        meta = self.describe(variable)
        dims = meta['dimensions']
        if not any(d['id'] == 0 for d in dims):
            raise AnalysisError('Time dimension required')
        years = self.years()
        lo = min(years) if first_year is None else first_year
        hi = max(years) if last_year is None else last_year
        if not isinstance(lo, int) or not isinstance(hi, int) or lo > hi or lo < min(years) or hi > max(years):
            raise AnalysisError(f'Invalid year range; available {min(years)}..{max(years)}')
        filters = {} if filters is None else filters
        if set(filters) - {d['column'] for d in dims if d['id'] != 0}:
            raise AnalysisError('Unknown dimension filter; use named dimension columns')
        selected = {}
        for dim in dims:
            values = filters.get(dim['column'], list(dim['buckets']))
            if not values or len(values) != len(set(values)) or set(values) - dim['buckets'].keys():
                raise AnalysisError(f"Invalid bucket selection for {dim['column']}")
            selected[dim['column']] = list(range(lo, hi + 1)) if dim['id'] == 0 else list(values)
        if variable not in self._cache:
            with readonly(self.path) as db:
                row = db.execute('SELECT Data FROM ifs_var_blob WHERE VariableName=?', (variable,)).fetchone()
            if row is None or row[0] is None:
                raise AnalysisError('Variable has no stored payload')
            blob = row[0]
            if ParquetFile(io.BytesIO(blob)).count() > self.registry.config.get('max_payload_rows', 5000000):
                raise AnalysisError('Payload exceeds configured row budget; no partial extraction performed')
            raw, encoding = decode(blob, self.dataset.get('encoding', 'standard'))
            expected_columns = [str(i) for i in range(len(dims))] + ['v']
            if set(raw.columns) != set(expected_columns):
                raise AnalysisError('Payload columns do not match declared dimensions')
            frame = raw.rename(columns={**{str(i): d['column'] for i, d in enumerate(dims)}, 'v': 'value'})
            keys = [d['column'] for d in dims]
            for dim in dims:
                col = frame[dim['column']]
                if col.isna().any() or not col.isin(dim['buckets']).all():
                    raise AnalysisError(f"Invalid dimension values: {dim['column']}")
                frame[dim['column']] = col.astype('int64')
            if frame.duplicated(keys).any():
                raise AnalysisError('Duplicate dimension keys in payload')
            frame['value'] = frame['value'].astype('float64')
            self._cache[variable] = frame, encoding
        frame, encoding = self._cache[variable]
        mask = np.ones(len(frame), dtype=bool)
        for col, values in selected.items():
            mask &= frame[col].isin(values).to_numpy()
        table = frame.loc[mask].copy()
        for dim in dims:
            if dim['id'] != 0:
                label = 'country' if dim['id'] == 1 else dim['column'] + '_label'
                table[label] = table[dim['column']].map(dim['buckets'])
        table = table.sort_values([d['column'] for d in dims]).reset_index(drop=True)
        expected = prod(len(v) for v in selected.values())
        invalid = int((~np.isfinite(table['value'])).sum())
        report = {'selection': selected, 'payload_rows': len(frame), 'expected_rows': expected,
                  'returned_rows': len(table), 'missing_rows': expected - len(table),
                  'nonfinite_values': invalid, 'complete': len(table) == expected and invalid == 0,
                  'truncated': False, 'decoder': encoding}
        self.assert_unchanged()
        return Selection(table, meta, report)
