from __future__ import annotations
import json
from urllib.parse import urlsplit
import httpx


class ProviderError(ValueError):
    pass


class IncompleteResponse(ProviderError):
    pass



def transport_error(exc, operation):
    """Diagnose connectivity without exposing URLs, headers, credentials or response bodies."""
    cause=exc; seen=set()
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        if getattr(cause,'winerror',None)==10013 or 'WinError 10013' in str(cause):
            return ProviderError('Network access is blocked by the app execution environment (Windows 10013). Restart the assistant from a normal PowerShell window using scripts/start-agent.ps1. This is not an API-key validation failure.')
        cause=cause.__cause__ or cause.__context__
    if isinstance(exc,httpx.TimeoutException):
        return ProviderError(operation+' timed out. Check connectivity and retry.')
    return ProviderError(operation+' failed. Check the connection and API compatibility.')


def validate_settings(value):
    mode = value.get('protocol', 'responses')
    if mode not in ('responses', 'chat_completions', 'anthropic'):
        raise ValueError('Choose Responses, Chat Completions or Anthropic Messages')
    endpoint = value.get('endpoint', '').strip().rstrip('/')
    u = urlsplit(endpoint)
    if u.username or u.password or u.query or u.fragment or not u.hostname:
        raise ValueError('Use an API base URL without credentials, query or fragment')
    if u.scheme != 'https' and not (u.scheme == 'http' and u.hostname in ('localhost','127.0.0.1','::1')):
        raise ValueError('Remote endpoints require HTTPS; HTTP is allowed only on loopback')
    if not value.get('model', '').strip() or len(value['model']) > 200:
        raise ValueError('Enter the exact model identifier exposed by your provider')
    key = value.get('api_key','')
    if not isinstance(key,str) or len(key)>4096 or '\n' in key or '\r' in key:
        raise ValueError('Invalid API key')
    return {'protocol': mode, 'endpoint': endpoint, 'model': value['model'].strip(), 'api_key':key}


def normalize_usage(raw, protocol):
    """Missing counters stay unavailable; never infer totals from character counts."""
    if not isinstance(raw,dict):return None
    def count(value):return value if isinstance(value,int) and not isinstance(value,bool) and value>=0 else None
    result={
        'input_tokens':count(raw.get('prompt_tokens',raw.get('input_tokens'))),
        'output_tokens':count(raw.get('completion_tokens',raw.get('output_tokens'))),
        'cached_input_tokens':count(raw.get('prompt_cache_hit_tokens',raw.get('cache_read_input_tokens',
            (raw.get('prompt_tokens_details') or raw.get('input_tokens_details') or {}).get('cached_tokens')))),
        'cache_write_input_tokens':count(raw.get('cache_creation_input_tokens')),
        'reasoning_tokens':count((raw.get('completion_tokens_details') or raw.get('output_tokens_details') or {}).get('reasoning_tokens')),
    }
    # Anthropic reports uncached input separately from cache reads/writes.
    if protocol=='anthropic' and result['input_tokens'] is not None:
        result['input_tokens']+=sum(result[k] or 0 for k in ('cached_input_tokens','cache_write_input_tokens'))
    return result


class Provider:
    def __init__(self, settings):
        self.settings = validate_settings(settings)
        self.last_usage = None
        self.stage = 'research'

    def request(self, conversation, tools, prompt):
        self.last_usage = None
        s = self.settings
        headers = {'Authorization': 'Bearer '+s['api_key']} if s['api_key'] else {}
        if s['protocol'] == 'anthropic':
            headers = {'x-api-key': s['api_key'], 'anthropic-version': '2023-06-01'}
            payload = {'model':s['model'], 'system':prompt, 'messages':conversation, 'max_tokens':6000,
                       'tools':[{'name':t['name'],'description':t['description'],'input_schema':t['inputSchema']} for t in tools]}
            route = '/messages'
        elif s['protocol'] == 'responses':
            payload = {'model':s['model'], 'instructions':prompt, 'input':conversation, 'store':False,
                       'max_output_tokens':6000,
                       'tools':[{'type':'function','name':t['name'],'description':t['description'],
                                 'parameters':t['inputSchema'],'strict':False} for t in tools]}
            route = '/responses'
        else:
            payload = {'model':s['model'], 'messages':[{'role':'system','content':prompt}, *conversation],
                       'max_tokens':6000, 'tools':[{'type':'function','function':{'name':t['name'],
                       'description':t['description'],'parameters':t['inputSchema']}} for t in tools]}
            route = '/chat/completions'
        if not tools:
            payload.pop('tools',None)
            if s['protocol'] in ('responses','chat_completions'):
                payload['tool_choice']='none'
        if self.stage.startswith('writer') and urlsplit(s['endpoint']).hostname=='api.deepseek.com':
            if s['protocol']=='chat_completions':
                payload['thinking']={'type':'disabled'}
                payload['response_format']={'type':'json_object'}
            elif s['protocol']=='responses':payload['reasoning']={'effort':'none'}
        # Do not follow redirects with credentials or use ambient proxy/auth settings.
        try:
            with httpx.Client(timeout=60, follow_redirects=False, trust_env=False) as client:
                with client.stream('POST',s['endpoint']+route,headers=headers,json=payload) as response:
                    if not 200 <= response.status_code < 300:
                        raise ProviderError(f'Provider returned HTTP {response.status_code}. Check protocol, endpoint, model and credentials in Settings.')
                    chunks=[]; size=0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 2_000_000: raise ProviderError('Provider response exceeded the 2 MB limit')
                        chunks.append(chunk)
                    data=json.loads(b''.join(chunks))
        except ProviderError:
            raise
        except Exception as exc:
            raise transport_error(exc,'Provider request') from None
        self.last_usage = normalize_usage(data.get('usage'),s['protocol'])
        try:
            if s['protocol']=='anthropic':
                if data.get('stop_reason') not in ('end_turn','tool_use'):
                    raise IncompleteResponse('Claude did not complete this turn; no final answer accepted')
                blocks=data['content']
                calls=[{'id':x['id'],'name':x['name'],'arguments':json.dumps(x['input'])} for x in blocks if x['type']=='tool_use']
                text='\n'.join(x['text'] for x in blocks if x['type']=='text')
                return [{'role':'assistant','content':blocks}],calls,text
            if s['protocol']=='responses':
                if data.get('status') not in (None,'completed'):
                    raise IncompleteResponse('Provider did not complete the response; no final answer accepted')
                output=data['output']
                calls=[{'id':x['call_id'],'name':x['name'],'arguments':x['arguments']} for x in output if x['type']=='function_call']
                text='\n'.join(p['text'] for x in output if x['type']=='message' for p in x.get('content',[]) if p['type']=='output_text')
                return output,calls,text
            choice=data['choices'][0]
            if choice.get('finish_reason') not in ('stop','tool_calls'):
                raise IncompleteResponse('Provider stopped before completion; no final answer accepted')
            message=choice['message']
            calls=[{'id':x['id'],'name':x['function']['name'],'arguments':x['function']['arguments']} for x in message.get('tool_calls',[])]
            # Preserve local providers' reasoning fields when present.
            return [message],calls,message.get('content') or ''
        except (KeyError,TypeError,IndexError):
            raise ProviderError('Provider response does not match the selected tool-calling protocol') from None

    def tool_output(self, call, value):
        content=json.dumps(value,ensure_ascii=False,default=str,allow_nan=False)
        if self.settings['protocol']=='anthropic':
            return {'role':'user','content':[{'type':'tool_result','tool_use_id':call['id'],'content':content}]}
        if self.settings['protocol']=='responses':
            return {'type':'function_call_output','call_id':call['id'],'output':content}
        return {'role':'tool','tool_call_id':call['id'],'content':content}
