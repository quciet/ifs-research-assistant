from __future__ import annotations
import hashlib
import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

class ResearchError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode('utf-8')).hexdigest()


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def search_expression(query):
    tokens = re.findall(r'\w+', query, re.UNICODE)[:20]
    if not tokens:
        raise ResearchError('Search requires at least one word or variable name')
    return ' AND '.join('"' + t.replace('"', '""') + '"' for t in tokens)


class Config:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.data = json.loads(self.path.read_text(encoding='utf-8-sig'))
        self.workspace = self.resolve(self.data['workspace'])
        self.code_root = self.resolve(self.data['code_root'])
        self.registry = self.resolve(self.data['results_registry'])
        protected = [self.code_root] + [self.resolve(p) for p in self.data.get('protected_roots', [])]
        if any(self.workspace == p or p in self.workspace.parents for p in protected):
            raise ResearchError('Research workspace overlaps a read-only source')
        self.workspace.mkdir(parents=True, exist_ok=True)

    def resolve(self, value):
        return (self.path.parent / value).resolve()


@contextmanager
def database(path):
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
