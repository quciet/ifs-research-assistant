from __future__ import annotations
from ifs_analysis.registry import Registry, fingerprint, readonly
from ifs_analysis.reader import Reader
from .common import Config, ResearchError
from .code_store import CodeStore
from .wiki_store import WikiStore


class Research:
    """Local tools; no model/provider dependency, network access only during explicit sync."""
    def __init__(self, config):
        self.config = config if isinstance(config, Config) else Config(config)
        self.code = CodeStore(self.config.workspace / 'code.sqlite3')
        self.wiki = WikiStore(self.config.workspace / 'wiki.sqlite3')

    def variable(self, name, dataset='IFsBase', limit=10):
        registry = Registry(self.config.registry)
        reader = Reader(registry, dataset)
        matches = [v for v in reader.variables() if v.casefold() == name.casefold()]
        metadata = reader.describe(matches[0]) if matches else None
        dictionary = None
        path = registry.config.get('variable_dictionary')
        dictionary_input = None
        if path:
            path = registry.resolve(path)
            dictionary_input = fingerprint(path)
            with readonly(path) as db:
                rows = db.execute('SELECT NAME, DEFINITION, UNITS, AGGREGATION FROM IFSVAR WHERE upper(NAME)=upper(?)', (name,)).fetchall()
                dictionary = [dict(r) for r in rows]
        return {
            'requested_symbol': name, 'dataset': dataset, 'results_metadata': metadata,
            'dictionary_matches': dictionary, 'dictionary_input': dictionary_input,
            'code': self.code.search(name, limit=limit, references=True),
            'documentation': self.wiki.search(name, limit=limit),
            'mapping_basis': 'Case-insensitive name matches only; no semantic equivalence inferred.',
            'compatibility': {'code_results': 'unverified', 'wiki_code': 'unverified', 'dictionary_results': 'unverified'},
            'notice': 'Missing results metadata means the symbol is not saved in this dataset. Documentation search absence is not proof of absent documentation.'
        }
