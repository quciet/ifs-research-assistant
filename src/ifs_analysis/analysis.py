from __future__ import annotations
import numpy as np
import pandas as pd
from .errors import AnalysisError


def _country_series(reader, variable, first_year=None, last_year=None):
    selection = reader.extract(variable, first_year, last_year).require_complete()
    meta = selection.metadata
    if (meta.get('Aggregation') or '').upper() != 'SUM':
        raise AnalysisError(f'{variable}: only verified SUM aggregation is implemented')
    sem = meta.get('semantics')
    if not sem or not sem.get('unit_family'):
        raise AnalysisError(f'{variable}: register reviewed variable semantics before aggregation')
    country_dim = next((d for d in meta['dimensions'] if d['id'] == 1), None)
    if country_dim is None:
        raise AnalysisError('World aggregation requires a country dimension')
    countries = reader.registry.countries()
    if any(country_dim['buckets'].get(k) != v for k, v in countries.items()):
        raise AnalysisError('Reviewed country membership does not match this dataset')
    extras = [d['id'] for d in meta['dimensions'] if d['id'] not in (0, 1)]
    if sorted(extras) != sorted(sem.get('sum_dimensions', [])):
        raise AnalysisError(f'{variable}: extra dimensions need explicit reviewed summation rules')
    for dim in meta['dimensions']:
        if dim['id'] in extras:
            approved = sem.get('summed_dimension_buckets', {}).get(str(dim['id']), {})
            approved = {int(k): v for k, v in approved.items()}
            if approved != dim['buckets']:
                raise AnalysisError(f'{variable}: summed dimension buckets differ from reviewed membership')
    frame = selection.table[selection.table.country_id.isin(countries)]
    series = frame.groupby(['year', 'country_id'], sort=True).value.sum(min_count=1)
    if not np.isfinite(series.to_numpy()).all():
        raise AnalysisError('Nonfinite aggregate')
    evidence = {'variable': variable, 'metadata': meta, 'coverage': selection.coverage,
                'world_members': countries,
                'excluded_region_ids': sorted(set(country_dim['buckets']) - set(countries))}
    return series, evidence


def _compatible(evidence):
    signatures = {(e['metadata']['semantics']['unit_family'], e['metadata'].get('Currency')) for e in evidence}
    if len(signatures) != 1:
        raise AnalysisError('Variables have incompatible unit families or currency codes')


def check_equality(reader, x, y, *, atol, rtol, first_year=None, last_year=None):
    if not np.isfinite([atol, rtol]).all() or atol < 0 or rtol < 0:
        raise AnalysisError('Tolerances must be finite and nonnegative')
    sx, ex = _country_series(reader, x, first_year, last_year)
    sy, ey = _country_series(reader, y, first_year, last_year)
    _compatible([ex, ey])
    if not sx.index.equals(sy.index):
        raise AnalysisError('Country/year coverage differs')
    wx, wy = sx.groupby(level='year').sum(), sy.groupby(level='year').sum()
    result = pd.DataFrame({'x': wx, 'y': wy})
    result['difference'] = result.x - result.y
    result['absolute_difference'] = result.difference.abs()
    result['tolerance'] = atol + rtol * np.maximum(result.x.abs(), result.y.abs())
    result['equal'] = result.absolute_difference <= result.tolerance
    result['stage'] = np.where(result.index == reader.years()[0], 'first_stored_year', 'subsequent_year')
    return result.reset_index(), {'x': ex, 'y': ey, 'atol': atol, 'rtol': rtol,
        'formula': 'abs(x-y) <= atol + rtol * max(abs(x), abs(y))',
        'all_equal': bool(result.equal.all()), 'failing_years': result.index[~result.equal].tolist(),
        'interpretation': 'Numerical comparison only; inequality is not a model-failure verdict.'}


def rank_gdp(reader, *, first_year, last_year, metric):
    if first_year >= last_year:
        raise AnalysisError('GDP ranking requires first_year < last_year')
    if metric not in ('absolute', 'percent', 'cagr'):
        raise AnalysisError('Metric must be absolute, percent, or cagr')
    series, evidence = _country_series(reader, 'GDP', first_year, last_year)
    if [d['id'] for d in evidence['metadata']['dimensions']] != [0, 1]:
        raise AnalysisError('GDP ranking requires exactly time and country dimensions')
    result = pd.DataFrame({'start_value': series.loc[first_year], 'end_value': series.loc[last_year]})
    result['status'] = 'included'
    if metric == 'absolute':
        result['growth'] = result.end_value - result.start_value
    else:
        valid = (result.start_value > 0) & (result.end_value >= 0)
        result.loc[~valid, 'status'] = 'excluded_nonpositive_start_or_negative_end'
        ratio = result.end_value / result.start_value.where(valid)
        result['growth'] = (ratio - 1) * 100 if metric == 'percent' else (ratio ** (1 / (last_year - first_year)) - 1) * 100
    if not np.isfinite(result.loc[result.status == 'included', 'growth']).all():
        raise AnalysisError('Nonfinite growth calculation')
    result = result.reset_index()
    result['country'] = result.country_id.map(reader.registry.countries())
    result = result.sort_values(['growth', 'country_id'], ascending=[False, True], na_position='last').reset_index(drop=True)
    result['rank'] = result.growth.rank(method='min', ascending=False).astype('Int64')
    evidence.update({'metric': metric, 'first_year': first_year, 'last_year': last_year,
                     'excluded_countries': result.loc[result.status != 'included', 'country'].tolist(),
                     'growth_units': evidence['metadata']['semantics']['unit_family'] if metric == 'absolute' else 'percent'})
    return result, evidence


def reconcile_investment(reader):
    frames, evidence = {}, []
    for variable in ['I', 'IGCF', 'INVS', 'IDS', 'PFD', 'MS', 'CS', 'GS', 'XS']:
        frames[variable], item = _country_series(reader, variable)
        evidence.append(item)
    _compatible(evidence)
    country = pd.DataFrame(frames)
    if country.isna().any().any():
        raise AnalysisError('Reconciliation variables have incompatible coverage')
    country['inventory_residual'] = country.PFD + country.MS - country.CS - country.GS - country.INVS - country.XS
    country['I_minus_IGCF'] = country.I - country.IGCF
    world = country.groupby(level='year').sum()
    forecast = country.loc[country.index.get_level_values('year') > reader.years()[0]]
    return world.reset_index(), {'variables': evidence, 'first_stored_year': reader.years()[0],
       'max_country_forecast_reconciliation_error': float((forecast.I_minus_IGCF - forecast.inventory_residual).abs().max()),
       'interpretation': 'Reproduces the prior arithmetic; excludes first stored year from forecast residual diagnostic. Does not establish causal validity.'}
