"""Conservative HTML extraction: keep structure and expose visual/dependency limitations."""
import re
from html.parser import HTMLParser

class Node:
    def __init__(self, tag='', attrs=None):
        self.tag, self.attrs, self.children = tag, dict(attrs or []), []

class DOM(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('root'); self.stack = [self.root]
    def handle_starttag(self, tag, attrs):
        node=Node(tag,attrs);self.stack[-1].children.append(node)
        if tag not in {'img','br','hr','meta','link','input','wbr','source','area','col','embed','param','track'}:
            self.stack.append(node)
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:
                del self.stack[i:];break
    def handle_data(self, data):self.stack[-1].children.append(data)


def extract_sections(html):
    dom=DOM();dom.feed(html)
    warnings=[]
    def render(node):
        if isinstance(node,str):return node
        if node.tag in {'script','style'} or 'mw-editsection' in node.attrs.get('class','').split():return ''
        if node.tag=='img':
            alt=node.attrs.get('alt','').strip()
            src=node.attrs.get('src','')
            warnings.append({'kind':'visual_not_transcribed','alt':alt,'source':src})
            return f'[Image reference: {alt or "unlabeled"}; {src}]'
        if node.tag=='math' and node.attrs.get('alttext'):
            return '[Math: '+node.attrs['alttext']+']'
        if 'mwe-math-element' in node.attrs.get('class','').split():
            def annotation(n):
                if isinstance(n,str):return None
                if n.tag=='annotation' and 'tex' in n.attrs.get('encoding',''):
                    return ''.join(c for c in n.children if isinstance(c,str))
                for c in n.children:
                    found=annotation(c)
                    if found:return found
            tex=annotation(node)
            if tex:return '[Math: '+tex+']'
        values=[render(child) for child in node.children]
        operands=[render(child) for child in node.children if isinstance(child,Node)] if node.tag in {'msub','msup','msubsup','mfrac','msqrt','mroot'} else []
        if node.tag=='msub' and len(operands)==2:return operands[0]+'_('+operands[1]+')'
        if node.tag=='msup' and len(operands)==2:return operands[0]+'^('+operands[1]+')'
        if node.tag=='msubsup' and len(operands)==3:return operands[0]+'_('+operands[1]+')^('+operands[2]+')'
        if node.tag=='mfrac' and len(operands)==2:return '('+operands[0]+')/('+operands[1]+')'
        if node.tag=='msqrt':return 'sqrt('+''.join(operands)+')'
        if node.tag=='mroot' and len(operands)==2:return 'root('+operands[0]+','+operands[1]+')'
        text=''.join(values)
        if node.tag=='math':
            warnings.append({'kind':'mathml_conversion_requires_visual_check'})
            return '\n[MathML transcription: '+text+']\n'
        if node.tag=='mtr':return '\n'+text+'\n'
        if node.tag=='mtd':return text+' | '

        if node.tag=='sup':return '^('+text+')'
        if node.tag=='sub':return '_('+text+')'
        if node.tag in {'td','th'}:return text.strip()+' | '
        if node.tag=='li':return '\n- '+text.strip()+'\n'
        if node.tag=='br':return '\n'
        if node.tag in {'p','div','tr','table','ul','ol','dl','dt','dd','pre'}:return '\n'+text+'\n'
        return text
    sections=[];parts=[];heading='Introduction';anchor='';heading_path=[]
    def flush():
        text=''.join(parts)
        text=re.sub(r'[ \t\r\f\v]+',' ',text)
        text=re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+','\n\n',text).strip()
        if text:
            starts=list(range(0,len(text),5000))
            if len(starts)>1 and len(text)-starts[-1]<200:starts.pop()
            for part,start in enumerate(starts):
                end=starts[part+1] if part+1<len(starts) else len(text)
                sections.append({'heading':heading,'anchor':anchor,'text':text[start:end],
                                 'part':part,'part_offset':start})
        parts.clear()
    def walk(node):
        nonlocal heading,anchor,heading_path
        if isinstance(node,str):parts.append(node);return
        if re.fullmatch('h[1-6]',node.tag):
            flush()
            level=int(node.tag[1]);label=render(node).strip()
            heading_path=[x for x in heading_path if x[0]<level]+[(level,label)]
            heading=' / '.join(x[1] for x in heading_path)
            def identifier(n):
                if isinstance(n,str):return ''
                if n.attrs.get('id'):return n.attrs['id']
                return next((v for c in n.children if (v:=identifier(c))), '')
            anchor=identifier(node)
        elif node.tag in {'p','table','ul','ol','dl','pre','math','img','script','style'} or 'mwe-math-element' in node.attrs.get('class','').split():
            parts.append(render(node))
        else:
            for child in node.children:walk(child)
    walk(dom.root);flush()
    if not sections: warnings.append({'kind':'empty_extraction'})
    warnings=list({repr(w):w for w in warnings}.values())
    return sections,warnings
