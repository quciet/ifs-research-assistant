"""Provider-reported tokens and measured workflow costs; never price guesses."""
import json
import time


class Metrics:
    def __init__(self,emit):
        self.emit=emit;self.started=time.monotonic();self.requests=[];self.tools=[]

    def request(self,provider,messages,tools,prompt,stage):
        started=time.monotonic();error=None
        # Avoid inheriting usage from an earlier request after a transport error.
        if hasattr(provider,'last_usage'):provider.last_usage=None
        if hasattr(provider,'stage'):provider.stage=stage
        try:return provider.request(messages,tools,prompt)
        except Exception as exc:error=type(exc).__name__;raise
        finally:
            item={'stage':stage,'elapsed_seconds':round(time.monotonic()-started,3),
                  'input_characters':len(json.dumps(messages))+len(json.dumps(tools))+len(prompt),
                  'usage':getattr(provider,'last_usage',None),'error_type':error}
            self.requests.append(item);self.emit({'type':'usage','request':item,'summary':self.summary()})

    def summary(self):
        stages={}
        for stage in ('research','writer','writer_correction'):
            rows=[x for x in self.requests if x['stage']==stage]
            if not rows:continue
            totals={k:sum(x['usage'][k] for x in rows if x['usage'] and x['usage'].get(k) is not None)
                    if any(x['usage'] and x['usage'].get(k) is not None for x in rows) else None
                    for k in ('input_tokens','output_tokens','cached_input_tokens','cache_write_input_tokens','reasoning_tokens')}
            stages[stage]={'requests':len(rows),'reported_usage_requests':sum(x['usage'] is not None for x in rows),**totals}
        return {'model_requests':len(self.requests),'executed_tool_calls':sum(not x['cached'] for x in self.tools),
                'reused_tool_calls':sum(x['cached'] for x in self.tools),
                'retrieved_characters':sum(x['characters'] for x in self.tools if not x['cached']),
                'elapsed_seconds':round(time.monotonic()-self.started,2),'stages':stages,
                'notice':'Tokens are provider-reported; unavailable counts are null. Reasoning/cache counts may be subsets of totals. No cost estimate.'}
