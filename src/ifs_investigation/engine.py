from __future__ import annotations
import re
import numpy as np
import pandas as pd
from ifs_analysis.analysis import _country_series, _compatible
from ifs_research.common import ResearchError


def validate(spec):
    if spec.get('schema_version')!=1 or not spec.get('question'):
        raise ResearchError('Investigation requires schema_version=1 and a question')
    if spec.get('review_status')!='reviewed' or not spec.get('code_evidence'):
        raise ResearchError('Review supplied code and attach evidence before running numerical interpretation')
    checks=spec.get('checks',[])
    if not checks or len(checks)>50:raise ResearchError('Provide 1..50 bounded checks')
    ids=set();variables=set()
    evidence_ids={e['id'] for e in spec['code_evidence']}
    if len(evidence_ids)!=len(spec['code_evidence']):raise ResearchError('Duplicate code evidence IDs')
    claims=spec.get('code_explanation',[])
    if not claims:raise ResearchError('A reviewed code explanation is required')
    for claim in claims:
        if not claim.get('text') or not claim.get('code_evidence') or set(claim['code_evidence'])-evidence_ids:
            raise ResearchError('Every code explanation must cite reviewed evidence')
    for c in checks:
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',c['id']) or c['id'] in ids:raise ResearchError('Invalid/duplicate check ID')
        ids.add(c['id'])
        if c.get('purpose') not in ('observation','implemented_relation'):raise ResearchError('Unknown check purpose')
        if c.get('stage') not in ('all','first_stored_year','subsequent_year'):raise ResearchError('Unknown stage')
        if not c.get('explanation'):raise ResearchError('Each check requires a code-first explanation')
        if c['purpose']=='implemented_relation' and not c.get('code_evidence'):raise ResearchError('Implemented relationships require code citations')
        if set(c.get('code_evidence',[]))-evidence_ids:raise ResearchError('Unknown code citation')
        for side in ('lhs','rhs'):
            expr=c[side]
            if set(expr)-{'terms','floor'} or not expr.get('terms'):raise ResearchError('Only weighted sums and an optional floor are supported')
            for name,weight in expr['terms'].items():
                if not re.fullmatch(r'[A-Za-z_]\w*',name) or not isinstance(weight,(int,float)) or not np.isfinite(weight):raise ResearchError('Invalid variable/weight')
                variables.add(name)
            if 'floor' in expr and (not isinstance(expr['floor'],(int,float)) or not np.isfinite(expr['floor'])):raise ResearchError('Invalid floor')
        tol=[c.get('atol'),c.get('rtol')]
        if any(not isinstance(t,(int,float)) or not np.isfinite(t) or t<0 for t in tol):raise ResearchError('Explicit finite nonnegative tolerances required')
    if len(variables)>50:raise ResearchError('At most 50 variables per investigation')
    for p in spec.get('preconditions',[]):
        if p.get('status') not in ('established','unknown','contradicted'):raise ResearchError('Invalid precondition status')
        if not p.get('description') or (p['status']!='unknown' and not p.get('evidence')):raise ResearchError('Preconditions require descriptions and evidence for determinate status')
    return sorted(variables)


def classify(checks,compatibility,preconditions):
    """Observations never become failed model assertions."""
    conditions=[p['status'] for p in preconditions]
    relations=[c for c in checks if c['purpose']=='implemented_relation']
    if compatibility=='documented_mismatch' or 'contradicted' in conditions:return 'incompatible_inputs'
    if compatibility!='documented_match' or not conditions or 'unknown' in conditions or not relations or any(c['rows']==0 for c in relations):
        return 'insufficient_evidence'
    return 'potential_inconsistency' if any(c['outside_tolerance'] for c in relations) else 'supported'


def expression(frame,expr):
    value=sum(frame[v]*w for v,w in expr['terms'].items())
    return value.clip(lower=expr['floor']) if 'floor' in expr else value


def evaluate(reader,spec,compatibility='unknown'):
    variables=validate(spec)
    series={};metadata=[]
    period=spec.get('period',{})
    for v in variables:
        series[v],e=_country_series(reader,v,period.get('first_year'),period.get('last_year'))
        metadata.append(e)
    _compatible(metadata)
    first=next(iter(series.values())).index
    if any(not s.index.equals(first) for s in series.values()):raise ResearchError('Variable coverage differs')
    country=pd.DataFrame(series)
    countries=spec.get('country_ids')
    if countries is not None:
        if not countries or len(set(countries))!=len(countries) or set(countries)-set(reader.registry.countries()):raise ResearchError('Invalid country selection')
        country=country[country.index.get_level_values('country_id').isin(countries)]
    if country.empty:raise ResearchError('Empty selection')
    initial=reader.years()[0];rows=[];summaries=[]
    for c in spec['checks']:
        years=country.index.get_level_values('year')
        mask=years==initial if c['stage']=='first_stored_year' else years>initial if c['stage']=='subsequent_year' else np.ones(len(country),dtype=bool)
        selected=country.loc[mask]
        values=pd.DataFrame({'lhs':expression(selected,c['lhs']),'rhs':expression(selected,c['rhs'])})
        # Floor and other country-level operations happen before aggregation.
        world=values.groupby(level='year').sum()
        for grain,frame in [('country',values.reset_index()),('selected_country_total',world.reset_index())]:
            if grain!='country':frame['country_id']=pd.NA
            frame['difference']=frame.lhs-frame.rhs
            frame['tolerance']=c['atol']+c['rtol']*np.maximum(frame.lhs.abs(),frame.rhs.abs())
            if not np.isfinite(frame[['lhs','rhs','difference','tolerance']].to_numpy()).all():raise ResearchError('Nonfinite calculation')
            frame['within_tolerance']=frame.difference.abs()<=frame.tolerance
            frame['check_id']=c['id'];frame['grain']=grain;frame['purpose']=c['purpose']
            frame['stage']=np.where(frame.year==initial,'first_stored_year','subsequent_year')
            rows.append(frame)
        finite=(values.lhs-values.rhs).abs()
        tolerance=c['atol']+c['rtol']*np.maximum(values.lhs.abs(),values.rhs.abs())
        summaries.append({'id':c['id'],'purpose':c['purpose'],'stage':c['stage'],'rows':len(values),
            'outside_tolerance':int((finite>tolerance).sum()),'max_absolute_difference':float(finite.max()) if len(values) else None,
            'interpretation':'Observed difference; no equality requirement.' if c['purpose']=='observation' else 'Comparison to a reviewed code relationship, conditional on recorded preconditions and version provenance.',
            'explanation':c['explanation'],'code_evidence':c.get('code_evidence',[])})
    result=pd.concat(rows,ignore_index=True)
    result['country']=result.country_id.map(reader.registry.countries())
    evidence={'question':spec['question'],'user_expectation':spec.get('user_expectation'),
        'authority':'Supplied executable implementation; documentation is explanatory support.',
        'code_explanation':spec.get('code_explanation',[]),'code_assessment':'reviewed_supplied_implementation','checks':summaries,
        'numeric_consistency':'consistent_with_reviewed_relations' if all(c['rows'] and not c['outside_tolerance'] for c in summaries if c['purpose']=='implemented_relation') and any(c['purpose']=='implemented_relation' for c in summaries) else 'inspect_relation_checks',
        'value_units':metadata[0]['metadata']['semantics']['unit_family'],
        'outcome':classify(summaries,compatibility,spec.get('preconditions',[])),
        'compatibility':compatibility,'preconditions':spec.get('preconditions',[]),
        'coverage':metadata,'first_stored_year':initial,'selected_countries':list(dict.fromkeys(country.index.get_level_values('country_id').tolist())),
        'years':sorted(set(country.index.get_level_values('year'))),
        'notice':'A passing identity does not establish the generating code version. A difference is not by itself a model bug. First stored year is not automatically verified initialization.'}
    return country.reset_index(),result,evidence
