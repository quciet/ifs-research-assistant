"""Provider defaults and authenticated, bounded model discovery. No model names hardcoded."""
import json
import time
import httpx
from .provider import validate_settings, ProviderError, transport_error

PRESETS = {
    'openai': {'label':'OpenAI (ChatGPT)','endpoint':'https://api.openai.com/v1','protocol':'responses'},
    'gemini': {'label':'Google (Gemini)','endpoint':'https://generativelanguage.googleapis.com/v1beta/openai','protocol':'chat_completions'},
    'claude': {'label':'Anthropic (Claude)','endpoint':'https://api.anthropic.com/v1','protocol':'anthropic'},
    'deepseek': {'label':'DeepSeek (DeepSeek)','endpoint':'https://api.deepseek.com','protocol':'chat_completions'},
}


def list_models(settings):
    s=validate_settings({**settings,'model':'discovery'})
    headers={'Authorization':'Bearer '+s['api_key']} if s['api_key'] else {}
    if s['protocol']=='anthropic':
        headers={'x-api-key':s['api_key'],'anthropic-version':'2023-06-01'}
    models={}; seen=set(); params={}; started=time.monotonic()
    try:
        with httpx.Client(timeout=15,follow_redirects=False,trust_env=False) as client:
            for page in range(10):
                if time.monotonic()-started>30: raise ProviderError('Model discovery timed out. Retry or enter a model manually.')
                with client.stream('GET',s['endpoint']+'/models',headers=headers,params=params) as response:
                    if not 200<=response.status_code<300:
                        raise ProviderError(f'Model discovery returned HTTP {response.status_code}. Check the API key, base URL and protocol; you can also enter a model manually.')
                    chunks=[];size=0
                    for chunk in response.iter_bytes():
                        size+=len(chunk)
                        if size>2_000_000 or time.monotonic()-started>30:
                            raise ProviderError('Model discovery exceeded its response/time limit.')
                        chunks.append(chunk)
                    data=json.loads(b''.join(chunks))
                if not isinstance(data.get('data'),list): raise ProviderError('Endpoint did not return a supported model list. Enter a model manually.')
                for model in data['data']:
                    key=model.get('id')
                    if not isinstance(key,str) or not 0<len(key)<=200: raise ProviderError('Endpoint returned an invalid model identifier.')
                    label=model.get('display_name') or key
                    models[key]={'id':key,'label':str(label)[:250]}
                if len(models)>2000: raise ProviderError('Model list exceeded 2,000 entries; use a manual identifier.')
                # Anthropic and compatible APIs may expose a cursor. Never follow a supplied URL.
                token=data.get('nextPageToken')
                if token: params={'pageToken':token}
                elif data.get('has_more'):
                    cursor=data.get('last_id') or (data['data'][-1]['id'] if data['data'] else None)
                    if not cursor: raise ProviderError('Model list pagination is incomplete.')
                    params={'after_id' if s['protocol']=='anthropic' else 'after':cursor}
                else:
                    return {'models':list(models.values()),'complete':True,
                            'notice':'Live API model list. Availability does not guarantee tool support; choose a text model that supports tools.'}
                marker=json.dumps(params,sort_keys=True)
                if marker in seen: raise ProviderError('Model list pagination repeated; enter a model manually.')
                seen.add(marker)
        raise ProviderError('Model discovery reached its page limit; enter a model manually.')
    except ProviderError: raise
    except Exception as exc:
        raise transport_error(exc,'Model discovery') from None
