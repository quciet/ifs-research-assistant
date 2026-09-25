from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from ifs_analysis.registry import Registry, fingerprint
from ifs_research.common import Config, digest
from ifs_research.service import Research


def connect(project, folder):
    """Register and index supplied source without writing into the installation.

    Numerical profiles are reused only for byte-identical reviewed inputs. Unknown
    installations remain useful for source/documentation research, without guessing
    their result encodings, country membership or aggregation rules.
    """
    project = Path(project).resolve()
    root = Path(folder).resolve(strict=True)
    if not root.is_dir() or root == project or root in project.parents or project in root.parents:
        raise ValueError('Choose an IFs installation separate from the assistant project')
    candidates = [root/'Code.Ifs-Translation/src/IFs.Core', root/'src/IFs.Core', root/'IFs.Core', root]
    code = next((p for p in candidates if p.is_dir() and any(p.glob('*.vb'))), None)
    if code is None:
        code = next((p for p in candidates if p.is_dir() and (any(p.glob('*.cs')) or (p.name=='IFs.Core' and any(p.rglob('*.cs'))))), None)
    if code is None:
        raise ValueError('No supported VB/C# source root found. Select the development installation or IFs.Core folder.')
    destination = project/'workspace/agent/installations'/digest(str(root))[:16]
    destination.mkdir(parents=True, exist_ok=True)
    pilot = Registry(project/'resources/pilot.json')
    registered = {}
    profiles = json.loads((project/'resources/result-profiles.json').read_text(encoding='utf-8'))['profiles']
    # This strict profile gate deliberately does not infer compatibility by folder name.
    for file in sorted((root/'RUNFILES').glob('*.run.db')):
        match = profiles.get(fingerprint(file)['sha256'])
        if match:
            registered[file.name[:-7]] = {**match, 'path': str(file), 'scenario_file': None,
                'scenario_identity': file.name[:-7],
                'scenario_relationship': 'Generating scenario unknown; matching bytes do not prove code provenance.'}
    config = {'workspace': str(destination/'research'), 'code_root': str(code),
              'results_registry': str(destination/'results.json'), 'protected_roots': [str(root)],
              'wiki': json.loads((project/'resources/research.json').read_text(encoding='utf-8-sig'))['wiki']}
    registry = {**pilot.config, 'datasets': registered, 'code_source': str(code),
                'protected_roots': [str(root)], 'documentation': [], 'variable_dictionary': None,
                'country_membership': str(pilot.resolve(pilot.config['country_membership']))}
    if not registered:
        registry['variable_semantics'] = {}
    (destination/'results.json').write_text(json.dumps(registry, indent=2), encoding='utf-8')
    path = destination/'research.json'
    path.write_text(json.dumps(config, indent=2), encoding='utf-8')
    research = Research(path)
    research.code.index(code)
    cached = Config(project/'resources/research.json').workspace/'wiki.sqlite3'
    target = research.config.workspace/'wiki.sqlite3'
    if cached.exists() and not research.wiki.status().get('searchable_pages'):
        with sqlite3.connect(cached.as_uri()+'?mode=ro', uri=True) as src, sqlite3.connect(target) as dst:
            src.backup(dst)
    return str(path)
