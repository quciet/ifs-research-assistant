"""Local hybrid retrieval. No source text is sent to an embedding service.

SQLite holds immutable chunks and vector blobs; numpy performs cosine search.
An explicit prepare operation downloads the embedding model. Queries are offline.
"""
from __future__ import annotations
import json
import os
import re
from pathlib import Path
import numpy as np
from .common import database, digest, dump, ResearchError
from .structure import statements
from ifs_analysis.registry import fingerprint, readonly

MODEL='BAAI/bge-small-en-v1.5'
CHUNK_VERSION='source-sections-1'


class LocalEmbedding:
    def __init__(self,workspace,download=False):
        # Keep dependency caches and download scratch space in the project workspace.
        os.environ['HF_HOME']=str(Path(workspace)/'hf-cache')
        os.environ['HF_XET_CACHE']=str(Path(workspace)/'hf-cache'/'xet')
        os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
        from fastembed import TextEmbedding
        self.cache=Path(workspace)/'embedding-model'
        self.cache.mkdir(parents=True,exist_ok=True)
        self.model=TextEmbedding(model_name=MODEL,cache_dir=str(self.cache),local_files_only=not download,threads=min(4,os.cpu_count() or 1))
        from importlib.metadata import version
        files=[(p.relative_to(self.cache).as_posix(),digest(p.read_bytes())) for p in sorted(self.cache.rglob('*'))
               if p.is_file() and p.suffix in ('.onnx','.json','.txt') and '.cache' not in p.parts]
        self.identity=digest(dump([MODEL,version('fastembed'),files]))

    def embed(self,texts,query=False):
        method=self.model.query_embed if query else self.model.passage_embed
        return np.asarray(list(method(texts,batch_size=16)),dtype=np.float32)


class RetrievalStore:
    def __init__(self,research):
        self.research=research;self.path=research.config.workspace/'retrieval.sqlite3';self.encoder=None
        with database(self.path) as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS corpora(id TEXT PRIMARY KEY,manifest TEXT);
            CREATE TABLE IF NOT EXISTS chunks(corpus TEXT,id TEXT,payload TEXT,PRIMARY KEY(corpus,id));
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(corpus UNINDEXED,id UNINDEXED,body);
            CREATE TABLE IF NOT EXISTS vectors(model TEXT,hash TEXT,vector BLOB,PRIMARY KEY(model,hash));
            CREATE TABLE IF NOT EXISTS vector_ready(corpus TEXT,model TEXT,PRIMARY KEY(corpus,model));''')

    def manifest(self):
        r=self.research
        with database(r.wiki.path) as db:
            restricted=' AND page_id IN (SELECT page_id FROM wiki_scope_members)' if db.execute('SELECT 1 FROM wiki_scope').fetchone() else ''
            pages=[dict(x) for x in db.execute("SELECT page_id,snapshot,state FROM wiki_pages WHERE state!='unavailable'"+restricted+' ORDER BY page_id')]
        registry=json.loads(r.config.registry.read_text(encoding='utf-8-sig'))
        dictionary=registry.get('variable_dictionary')
        dictionary_input=fingerprint((r.config.registry.parent/dictionary).resolve()) if dictionary else None
        return {'code':r.code.current(),'wiki':getattr(r.wiki,'pinned_pages',pages),'dictionary':dictionary_input,'chunker':CHUNK_VERSION}

    def build(self):
        manifest=self.manifest();cid=digest(dump(manifest))
        with database(self.path) as db:
            if db.execute('SELECT 1 FROM corpora WHERE id=?',(cid,)).fetchone():return cid
        chunks=[]
        def append(item):
            item['id']=digest(dump(item));item['embedding_text']=(item['label']+'\n'+item['text'])[:1200]
            item['embedding_excerpt']=len(item['label'])+len(item['text'])+1>1200
            item['embedding_hash']=digest(item['embedding_text']);chunks.append(item)
        with database(self.research.code.path) as db:
            files=db.execute('SELECT path,body,sha256 FROM code_files WHERE snapshot=?',(manifest['code'],)).fetchall()
        for f in files:
            lines=f['body'].splitlines()
            source=list(statements(f['body'])) if f['path'].endswith('.vb') else [(n,n,t,t) for n,t in enumerate(f['body'].splitlines(),1) if t.strip()]
            group=[];length=0
            def flush():
                if not group:return
                a,b=group[0][0],group[-1][1]
                text='\n'.join(lines[a-1:b])
                append({'kind':'code','label':f['path'],'text':text,
                        'citation':{'snapshot':manifest['code'],'path':f['path'],'sha256':f['sha256'],'start':a,'end':b}})
            for row in source:
                if group and (length+len(row[3])>1100 or row[1]-group[0][0]>60):flush();group=[];length=0
                group.append(row);length+=len(row[3])
            flush()
        with database(self.research.wiki.path) as db:
            for page in manifest['wiki']:
                rows=db.execute('SELECT id,heading,body FROM wiki_sections WHERE snapshot=? ORDER BY part,id',(page['snapshot'],)).fetchall()
                for row in rows:
                    info=self.research.wiki.read(row['id'],length=1)
                    # Each section retains exact offsets; long paragraphs are marked excerpts.
                    for offset in range(0,len(row['body']),1000):
                        append({'kind':'wiki','label':info['title']+' / '+row['heading'],
                                'text':row['body'][offset:offset+1000],'section_id':row['id'],'offset':offset,
                                'citation':info['citation'],'snapshot':info['snapshot'],'revision':info['revision'],
                                'selection':info['selection'],'approval':info['approval'],'cache_status':page['state'],
                                'section_excerpt':offset>0 or len(row['body'])>1000})
        if manifest['dictionary']:
            with readonly(manifest['dictionary']['path']) as db:
                for row in db.execute('SELECT NAME,DEFINITION,UNITS,AGGREGATION FROM IFSVAR'):
                    append({'kind':'variable_metadata','label':str(row['NAME']),
                        'text':dump(dict(row)),'citation':{'dictionary_sha256':manifest['dictionary']['sha256'],'variable':row['NAME']},
                        'compatibility':'Name match only; dictionary/code/results version relationship unverified.'})
        # Activation is atomic and refuses a mixed source generation.
        if self.manifest()!=manifest:raise ResearchError('Sources changed during retrieval indexing; retry')
        with database(self.path) as db:
            if not db.execute('SELECT 1 FROM corpora WHERE id=?',(cid,)).fetchone():
                db.executemany('INSERT INTO chunks VALUES(?,?,?)',[(cid,x['id'],dump(x)) for x in chunks])
                db.executemany('INSERT INTO chunk_fts VALUES(?,?,?)',[(cid,x['id'],x['label']+'\n'+x['text']) for x in chunks])
                db.execute('INSERT INTO corpora VALUES(?,?)',(cid,dump(manifest)))
        return cid

    def prepare(self,download=False,encoder=None,progress=lambda x:None):
        cid=self.build();self.encoder=encoder or LocalEmbedding(self.research.config.workspace,download)
        model=self.encoder.identity
        with database(self.path) as db:
            chunks=[json.loads(x[0]) for x in db.execute('SELECT payload FROM chunks WHERE corpus=?',(cid,))]
            existing={x[0] for x in db.execute('SELECT hash FROM vectors WHERE model=?',(model,))}
        missing={x['embedding_hash']:x['embedding_text'] for x in chunks if x['embedding_hash'] not in existing}
        items=list(missing.items())
        for start in range(0,len(items),32):
            batch=items[start:start+32];vectors=self.encoder.embed([x[1] for x in batch])
            vectors=self.validate_vectors(vectors,len(batch))
            with database(self.path) as db:
                db.executemany('INSERT OR REPLACE INTO vectors VALUES(?,?,?)',[(model,h,v.astype('<f4').tobytes()) for (h,_),v in zip(batch,vectors)])
            progress({'embedded':min(start+32,len(items)),'needed':len(items)})
        with database(self.path) as db:db.execute('INSERT OR REPLACE INTO vector_ready VALUES(?,?)',(cid,model))
        settings={'model':MODEL,'identity':model}
        dest=self.research.config.workspace/'semantic.json';temp=dest.with_suffix('.tmp')
        temp.write_text(dump(settings),encoding='utf-8');temp.replace(dest)
        return {'corpus':cid,'chunks':len(chunks),'embedded':len(items),'reused':len(chunks)-len(items),'model_identity':model}

    @staticmethod
    def validate_vectors(values,count):
        values=np.asarray(values,dtype=np.float32)
        if values.ndim!=2 or len(values)!=count or not np.isfinite(values).all():raise ResearchError('Invalid local embedding output')
        norms=np.linalg.norm(values,axis=1,keepdims=True)
        if (norms==0).any():raise ResearchError('Zero embedding vector')
        return values/norms

    def search(self,query,limit=6,corpus=None,semantic=True,kind="all"):
        if kind not in ('all','code','wiki','variable_metadata'):raise ResearchError('Invalid retrieval kind')
        cid=corpus or self.build();words=re.findall(r'\w+',query)[:24]
        if not words:raise ResearchError('Search requires words')
        with database(self.path) as db:
            restriction='' if kind=='all' else " AND id IN (SELECT id FROM chunks WHERE corpus=? AND json_extract(payload,'$.kind')=?)"
            ranked=[]
            for operator in (' AND ',' OR '):
                expression=operator.join('"'+w+'"' for w in words)
                ranked.append([r[0] for r in db.execute('SELECT id FROM chunk_fts WHERE chunk_fts MATCH ? AND corpus=?'+restriction+' ORDER BY bm25(chunk_fts) LIMIT 24',(expression,cid) if kind=='all' else (expression,cid,cid,kind))])
            chunks={r[0]:json.loads(r[1]) for r in db.execute('SELECT id,payload FROM chunks WHERE corpus=?',(cid,))}
        if kind!='all':chunks={k:v for k,v in chunks.items() if v['kind']==kind}
        status='disabled' if not semantic else 'unavailable; exact/text search used'
        config=self.research.config.workspace/'semantic.json'
        if semantic and config.exists():
            try:
                settings=json.loads(config.read_text(encoding='utf-8'))
                if self.encoder is None:self.encoder=LocalEmbedding(self.research.config.workspace)
                if self.encoder.identity!=settings['identity']:raise ResearchError('Embedding model changed; rebuild required')
                with database(self.path) as db:
                    if not db.execute('SELECT 1 FROM vector_ready WHERE corpus=? AND model=?',(cid,self.encoder.identity)).fetchone():raise ResearchError('Vectors need refreshing for these sources')
                    vectors={r[0]:np.frombuffer(r[1],dtype='<f4') for r in db.execute('SELECT hash,vector FROM vectors WHERE model=?',(self.encoder.identity,))}
                q=self.validate_vectors(self.encoder.embed([query],query=True),1)[0]
                scores=[(float(np.dot(q,vectors[x['embedding_hash']])),key) for key,x in chunks.items()]
                ranked.append([key for score,key in sorted(scores,reverse=True)[:24]])
                status='local embeddings active'
            except Exception as exc:
                # No fallback to online embeddings, no source data in error text.
                status='unavailable; exact/text search used ('+type(exc).__name__+')'
        combined={}
        for i,ranking in enumerate(ranked):
            for rank,key in enumerate(ranking):combined[key]=combined.get(key,0)+(2 if i==0 else 1)/(60+rank)
        hits=[]
        for key in sorted(combined,key=combined.get,reverse=True)[:limit]:
            x=chunks[key];hits.append({k:v for k,v in x.items() if k not in ('embedding_text','embedding_hash')})
            hits[-1]['text']=x['text'][:1400];hits[-1]['preview_truncated']=len(x['text'])>1400
        return {'corpus':cid,'semantic_status':status,'hits':hits,
                'notice':'Search relevance is not causal evidence. Read cited source context before concluding; previews and embedding excerpts can be incomplete.'}
