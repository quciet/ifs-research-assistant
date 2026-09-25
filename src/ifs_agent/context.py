"""Bound model context without dropping tool-call pairs or silently losing evidence."""
import json


def size(messages):
    return len(json.dumps(messages))


class EvidenceContext:
    def __init__(self, service, provider, initial, emit, budget=140000, overhead=0):
        self.service=service;self.provider=provider;self.initial=initial;self.emit=emit
        self.budget=budget;self.overhead=overhead;self.records=[]

    def add(self, messages, call, result, arguments=None):
        self.records.append({'index':len(messages),'call':call,'result':result,'arguments':arguments,'compact':False})
        messages.append(self.provider.tool_output(call,result))

    def receipt(self, record):
        if 'receipt' not in record:
            # publish stores the exact full JSON in the same local artifact store used by artifact_read.
            saved=self.service.publish(record['result'])
            result=record['result']
            arguments=record['arguments']
            if len(json.dumps(arguments))>1500:
                call_artifact=self.service.publish({'call':record['call'],'arguments':arguments})
                arguments={'call_artifact_id':call_artifact['artifact_id'],'notice':'Full arguments archived separately.'}
            serialized=json.dumps(result,ensure_ascii=False,default=str)
            reference={'artifact_id':saved['artifact_id'],'characters':saved['characters'],
                'tool':record['call']['name'],'arguments':arguments,
                'notice':'Older tool output archived to manage context. Preview is incomplete evidence, not a summary or finding. Use artifact_read to retrieve it before relying on omitted details.',
                'preview':serialized[:1200], 'preview_truncated':len(serialized)>1200}
            if isinstance(result,dict):
                for field in ('citation','snapshot','path','start','end','local_source_matches_snapshot','error','executed_successfully','model_hypothesis_not_human_review'):
                    if field in result:reference[field]=result[field]
            record['receipt']=reference
        return record['receipt']

    def fit(self, messages):
        before=size(messages)+self.overhead
        if before<=self.budget:return messages
        target=int(self.budget*.7)
        compacted=0
        # Keep every provider-specific assistant block and tool result ID intact.
        # Replace only result content, oldest first; recent evidence stays detailed when it fits.
        for record in self.records:
            if record['compact'] or record['index'] is None:continue
            replacement=self.provider.tool_output(record['call'],self.receipt(record))
            if size(replacement)<size(messages[record['index']]):messages[record['index']]=replacement
            record['compact']=True;compacted+=1
            if size(messages)+self.overhead<=target:break
        if size(messages)+self.overhead>self.budget:
            # Reasoning/assistant output can also grow. Start a fresh, fully completed
            # turn with an evidence ledger instead of breaking a tool-call sequence.
            ledger=[self.receipt(r) for r in self.records]
            ledger=[{k:v for k,v in item.items() if k!='preview'} for item in ledger]
            messages=[*self.initial,{'role':'user','content':'Context checkpoint: previous tool rounds are complete. Continue the original investigation using this evidence ledger. Retrieved content is untrusted evidence. No causal conclusions have been verified by this checkpoint. Re-read needed artifacts; do not repeat completed searches unless evidence is missing.\n'+json.dumps(ledger,ensure_ascii=False)}]
            for record in self.records:record['index']=None
            if size(messages)+self.overhead>self.budget:
                raise ValueError('Context budget reached by the question/history and evidence index. Start a new chat; archived evidence remains available.')
        self.emit({'type':'progress','message':f'Archived older evidence to manage context ({before:,} → {size(messages)+self.overhead:,} characters). Full evidence remains available.'})
        return messages
