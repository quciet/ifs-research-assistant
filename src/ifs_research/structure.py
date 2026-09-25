"""Conservative VB statement navigation, not compiler binding or a causal graph.

Cached per file hash/parser version. Unsupported constructs are retained as
warnings instead of silently converted into dependencies.
"""
from __future__ import annotations
import json
import re
from .common import database, digest, dump, ResearchError
from .code_store import clean_vb, routines, phase

VERSION='vb-structure-2'
IDENT=r'[A-Za-z_]\w*'
WORDS=set(('as dim public private friend protected shared const static single double integer long boolean string '
           'if then else elseif end and or not andalso orelse mod true false nothing new byval byref optional '
           'for each to step next while do loop until return call sub function property select case try catch '
           'finally with redim preserve get set let is isnot me global math').split())


def identifiers(text):
    return sorted({x.casefold() for x in re.findall(IDENT,text) if x.casefold() not in WORDS})


def statements(body):
    """Join explicit continuation and balanced parentheses, preserving line spans."""
    lines=body.splitlines();parts=[];start=1;depth=0
    for n,line in enumerate(lines,1):
        code=clean_vb(line).strip()
        if not code:continue
        if not parts:start=n
        explicit=bool(re.search(r'\s_\s*$',code))
        code=re.sub(r'\s_\s*$','',code)
        parts.append(code);depth+=code.count('(')-code.count(')')
        implicit=bool(re.search(r'(?:[=,+*/&\-]|\b(?:AndAlso|OrElse|And|Or))\s*$',code,re.I))
        if explicit or depth>0 or implicit:continue
        yield start,n,' '.join(parts),'\n'.join(lines[start-1:n])
        parts=[];depth=0
    if parts:yield start,len(lines),' '.join(parts),'\n'.join(lines[start-1:])


def split_top(text,separator=','):
    depth=0;start=0
    for i,ch in enumerate(text):
        if ch=='(':depth+=1
        elif ch==')':depth-=1
        elif ch==separator and depth==0:
            yield text[start:i];start=i+1
    yield text[start:]


def assignment(code):
    code=re.sub(r'^\s*(?:Let|Set)\s+','',code,flags=re.I)
    match=re.match(r'('+IDENT+r'(?:\.'+IDENT+r')*)',code)
    if not match:return None
    i=match.end();target=match.group(1)
    if i<len(code) and code[i] in '%!#$&@':target+=code[i];i+=1
    rest=code[i:].lstrip()
    if rest.startswith('('):
        depth=0;end=None
        for j,ch in enumerate(rest):
            if ch=='(':depth+=1
            elif ch==')':
                depth-=1
                if depth==0:end=j+1;break
        if end is None:return None
        target+=rest[:end];rest=rest[end:].lstrip()
    op=re.match(r'(\+=|-=|\*=|/=|\\=|\^=|&=|=(?!=))(.*)$',rest)
    if not op:return None
    return target,match.group(1),op.group(1),op.group(2).strip()


def parse_vb(body,path):
    rs=routines(body.splitlines());records=[];warnings=[];stack=[]
    for start,end,code,raw in statements(body):
        routine=next((r for r in rs if r['start']<=start<=r['end']),None)
        base={'start':start,'end':end,'text':raw,'routine':routine['name'] if routine else None,
              'routine_start':routine['start'] if routine else None,'phase':phase(path)}
        low=code.casefold()
        # Never turn colon-separated/inline conditional statements into guessed edges.
        if ':' in code or code.startswith('#') or re.search(r'\b(?:Function|Sub)\s*\(',code,re.I):
            warnings.append({**base,'reason':'Unsupported colon, directive, or lambda; inspect source'})
            continue
        if re.match(r'end\s+(if|select|try|with)|next\b|wend\b|end\s+while|loop\b',low):
            if stack:stack.pop()
            else:warnings.append({**base,'reason':'Unmatched block end'})
            continue
        if re.match(r'end\s+(sub|function|property)',low):
            stack=[];continue
        if re.match(r'(elseif|else|case|catch|finally)\b',low):
            if stack:
                if not stack[-1].get('branches'):stack[-1]['branches']=[stack[-1]['text']]
                stack[-1]['branches'].append(code)
                stack[-1]['text']=code;stack[-1]['line']=start
            else:warnings.append({**base,'reason':'Unmatched branch'})
            continue
        if re.match(r'if\b',low):
            if not re.search(r'\bthen\s*$',low):
                warnings.append({**base,'reason':'Single-line If not structurally resolved'})
                continue
            stack.append({'text':code,'line':start});continue
        if re.match(r'(for|while|do|select\s+case|try|with)\b',low):
            stack.append({'text':code,'line':start});continue
        base['conditions']=json.loads(dump(stack))
        declaration=re.match(r'(?:(?:Public|Private|Friend|Protected|Shared|Static|Dim|Const|ReadOnly)\s+)+(.+)$',code,re.I)
        if declaration and not re.match(r'(?:Sub|Function|Property|Module|Class|Structure)\b',declaration.group(1),re.I):
            for part in split_top(declaration.group(1)):
                name=re.match(r'\s*('+IDENT+r')',part)
                if name:
                    records.append({**base,'kind':'declaration','symbol':name.group(1).casefold(),'expression':part.strip()})
                    if '=' in part:
                        rhs=part.split('=',1)[1].strip()
                        records.append({**base,'kind':'assignment','symbol':name.group(1).casefold(),'target':name.group(1),
                            'operator':'=','expression':rhs,'inputs':identifiers(rhs),'index_references':[],
                            'declaration_initializer':True,'binding':'syntactic; scope not compiler-resolved'})
            continue
        found=assignment(code)
        if found:
            target,symbol,operator,rhs=found
            inputs=identifiers(rhs)
            if operator!='=':inputs=sorted(set(inputs+[symbol.casefold()]))
            records.append({**base,'kind':'assignment','symbol':symbol.casefold(),'target':target,
                'operator':operator,'expression':rhs,'inputs':inputs,
                'index_references':identifiers(target[len(symbol):]),
                'binding':'syntactic; array/function references and scope not compiler-resolved'})
        elif '=' in code and not re.match(r'(?:Return|Exit|Throw|Imports|Namespace|End|Public|Private|Friend|Sub|Function|Property)\b',code,re.I):
            warnings.append({**base,'reason':'Possible assignment or comparison not structurally resolved'})
        # Parenthesized identifiers could be calls OR array accesses: retain ambiguity.
        for name in sorted(set(re.findall(r'('+IDENT+r'(?:\.'+IDENT+r')*)\s*\(',code))):
            records.append({**base,'kind':'call_candidate','symbol':name.casefold(),
                            'binding':'Unresolved: function invocation or array access'})
    return {'records':records,'warnings':warnings,'routines':rs,
            'limitations':['No compiler binding, alias/ByRef effects, or conditional-compilation evaluation.',
                          'Conditions are enclosing source text, not evaluated predicates.',
                          'File-based phase labels are hints; forecast routines may initialize first-year values.']}


class StructureStore:
    def __init__(self,code):
        self.code=code;self.path=code.path.parent/'structure.sqlite3'
        with database(self.path) as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS parsed_files(key TEXT PRIMARY KEY,payload TEXT);
            CREATE TABLE IF NOT EXISTS members(snapshot TEXT,path TEXT,key TEXT,sha TEXT,PRIMARY KEY(snapshot,path));
            CREATE TABLE IF NOT EXISTS records(snapshot TEXT,path TEXT,start INTEGER,kind TEXT,symbol TEXT,payload TEXT);
            CREATE INDEX IF NOT EXISTS symbol_index ON records(snapshot,symbol,kind);
            CREATE TABLE IF NOT EXISTS ready(snapshot TEXT PRIMARY KEY,version TEXT,report TEXT);''')

    def build(self,snapshot=None):
        sid=snapshot or self.code.current()
        with database(self.path) as db:
            old=db.execute('SELECT report FROM ready WHERE snapshot=? AND version=?',(sid,VERSION)).fetchone()
            if old:return {**json.loads(old[0]),'already_current':True,'parsed':0,'reused':db.execute('SELECT count(*) FROM members WHERE snapshot=?',(sid,)).fetchone()[0]}
        with database(self.code.path) as db:
            files=db.execute('SELECT path,sha256,body FROM code_files WHERE snapshot=?',(sid,)).fetchall()
        counts={'parsed':0,'reused':0,'unsupported_files':0,'records':0,'warnings':0}
        with database(self.path) as db:
            db.execute('DELETE FROM records WHERE snapshot=?',(sid,))
            for f in files:
                key=digest(dump([VERSION,f['path'],f['sha256']]))
                cached=db.execute('SELECT payload FROM parsed_files WHERE key=?',(key,)).fetchone()
                if cached:parsed=json.loads(cached[0]);counts['reused']+=1
                else:
                    parsed=parse_vb(f['body'],f['path']) if f['path'].lower().endswith('.vb') else {
                        'records':[],'routines':[],'warnings':[{'reason':'Unsupported language; use lexical search'}]}
                    db.execute('INSERT OR REPLACE INTO parsed_files VALUES(?,?)',(key,dump(parsed)));counts['parsed']+=1
                counts['unsupported_files']+=int(not f['path'].lower().endswith('.vb'))
                counts['warnings']+=len(parsed['warnings']);counts['records']+=len(parsed['records'])
                db.execute('INSERT OR REPLACE INTO members VALUES(?,?,?,?)',(sid,f['path'],key,f['sha256']))
                db.executemany('INSERT INTO records VALUES(?,?,?,?,?,?)',[(sid,f['path'],r['start'],r['kind'],r['symbol'],dump(r)) for r in parsed['records']])
            report={'snapshot':sid,'parser':VERSION,**counts}
            db.execute('INSERT OR REPLACE INTO ready VALUES(?,?,?)',(sid,VERSION,dump(report)))
        return report

    def lookup(self,symbol,kind='all',offset=0,limit=8,snapshot=None,path=None):
        if not re.fullmatch(IDENT+r'(?:\.'+IDENT+r')*',symbol):raise ResearchError('Use one variable or qualified name')
        if kind not in ('all','assignment','declaration','uses','call_candidate'):raise ResearchError('Invalid structure query')
        sid=snapshot or self.code.current();self.build(sid)
        with database(self.path) as db:
            if kind=='uses':
                rows=db.execute("SELECT * FROM records WHERE snapshot=? AND kind='assignment' AND EXISTS (SELECT 1 FROM json_each(records.payload,'$.inputs') WHERE value=?) ORDER BY path,start",(sid,symbol.casefold())).fetchall()
            else:
                sql='SELECT * FROM records WHERE snapshot=? AND symbol=?';params=[sid,symbol.casefold()]
                if kind!='all':sql+=' AND kind=?';params.append(kind)
                rows=db.execute(sql+' ORDER BY path,start',params).fetchall()
            if path is not None:rows=[r for r in rows if r['path']==path]
            results=[]
            for row in rows[offset:offset+limit]:
                record=json.loads(row['payload'])
                record['citation']={'snapshot':sid,'path':row['path'],'start':record['start'],'end':record['end']}
                record['routine_id']=f"{sid}:{row['path']}:{record['routine_start']}" if record['routine_start'] else None
                if record['kind']=='call_candidate':
                    with database(self.code.path) as code_db:
                        candidates=[dict(x) for x in code_db.execute('SELECT id,path,name,start,end FROM code_routines WHERE snapshot=? AND lower(name)=?',(sid,symbol.split('.')[-1].casefold()))]
                    record['routine_candidates']=candidates[:8]
                    record['binding']='Name-match candidates only; scope/overload binding unresolved'
                results.append(record)
        return {'snapshot':sid,'symbol':symbol,'kind':kind,'total':len(rows),'hits':results,
                'next_offset':offset+limit if offset+limit<len(rows) else None,
                'limitations':'Syntactic navigation, not a complete dependency graph. Conditions may omit unsupported or preprocessor constructs. Missing matches do not prove absence. Check warnings with routine_context.'}

    def scopes(self,path,start,end,snapshot=None):
        sid=snapshot or self.code.current();self.build(sid)
        with database(self.path) as db:
            rows=db.execute("SELECT payload FROM records WHERE snapshot=? AND path=? AND start BETWEEN ? AND ? AND kind='assignment' ORDER BY start",(sid,path,start,end)).fetchall()
        groups={}
        for row in rows:
            record=json.loads(row[0]);conditions=record.get('conditions',[])
            key=dump([record['routine'],conditions])
            if key not in groups:groups[key]={'routine':record['routine'],'conditions':conditions,'example_line':record['start']}
        values=list(groups.values())
        return {'contexts':values[:6],'distinct_contexts':len(values),'truncated':len(values)>6,
                'notice':'Apply each statement only under its own conditions. Initialization and forecast branches may coexist in this excerpt; do not generalize a first-year cap or calibration into a forecast rule. These are syntactic contexts, not evaluated predicates.'}

    def context(self,path,start,snapshot=None):
        sid=snapshot or self.code.current();self.build(sid)
        with database(self.path) as db:
            row=db.execute('SELECT p.payload FROM parsed_files p JOIN members m ON p.key=m.key WHERE m.snapshot=? AND m.path=?',(sid,path)).fetchone()
        if not row:raise ResearchError('Unknown source file')
        data=json.loads(row[0]);routine=next((r for r in data['routines'] if r['start']<=start<=r['end']),None)
        records=[r for r in data['records'] if r['start']<=start<=r['end']]
        lo=routine['start'] if routine else max(1,start-8);hi=routine['end'] if routine else start+8
        warnings=[w for w in data['warnings'] if lo<=w.get('start',start)<=hi]
        nearby=sorted(warnings,key=lambda w:abs(w.get('start',start)-start))[:5]
        return {'source':self.code.read(path,max(1,start-6),start+12,sid),
                'routine':routine,'statements':records,'warnings':nearby,'routine_warning_count':len(warnings),
                'warnings_truncated':len(warnings)>len(nearby)}
