"""Reproducible example jobs. No model connection or IFs execution."""
from pathlib import Path
from ifs_analysis.jobs import run_job

root = Path(__file__).resolve().parents[1]
registry = root / 'resources/pilot.json'
for dataset in ('IFsBase', 'Working'):
    print(run_job(registry, dataset, 'equality',
                  {'x': 'I', 'y': 'IGCF', 'atol': 0.001, 'rtol': 1e-6}, root / 'workspace/jobs'))
    print(run_job(registry, dataset, 'gdp-ranking',
                  {'first_year': 2022, 'last_year': 2050, 'metric': 'cagr'}, root / 'workspace/jobs'))
