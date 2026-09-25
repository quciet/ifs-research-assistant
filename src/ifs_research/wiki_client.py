"""Read-only MediaWiki transport and verified article-revision selection."""
from __future__ import annotations
import json
import re
import time
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib import request, parse, error
from .common import ResearchError, digest, now


class MissingPage(ResearchError):
    pass


class Transport:
    def __init__(self, api, interval=1.0, opener=None, sleep=time.sleep, clock=time.monotonic):
        self.api = api
        origin = parse.urlsplit(api)
        if origin.scheme != 'https' or not origin.netloc:
            raise ResearchError('Wiki API must use HTTPS')
        self.origin = (origin.scheme, origin.netloc)
        self.index = parse.urljoin(api, 'index.php')
        self.interval = max(1.0, interval)
        self.opener = opener or request.urlopen
        self.sleep, self.clock, self.last = sleep, clock, None
        self.requests = 0

    def get(self, url):
        if parse.urlsplit(url)[:2] != self.origin:
            raise ResearchError('Cross-origin wiki request refused')
        for attempt in range(3):
            if self.last is not None:
                self.sleep(max(0, self.interval - (self.clock() - self.last)))
            self.last = self.clock()
            self.requests += 1
            try:
                req = request.Request(url, headers={'User-Agent': 'IFsResearchAssistant/0.1 (read-only documentation sync)',
                                                   'Cache-Control': 'no-cache'})
                with self.opener(req, timeout=30) as response:
                    if parse.urlsplit(response.geturl())[:2] != self.origin:
                        raise ResearchError('Cross-origin wiki redirect refused')
                    body = response.read(16 * 1024 * 1024 + 1)
                    if len(body) > 16 * 1024 * 1024:
                        raise ResearchError('Wiki response exceeds 16 MiB budget')
                    try:return body.decode('utf-8')
                    except UnicodeDecodeError as exc:raise ResearchError('Wiki response is not UTF-8') from exc
            except error.HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise ResearchError(f'Wiki HTTP error {exc.code}') from exc
                wait = 2 ** attempt
                retry = exc.headers.get('Retry-After')
                if retry:
                    try: wait = max(wait, float(retry))
                    except ValueError:
                        try: wait = max(wait, (parsedate_to_datetime(retry) - datetime.now(timezone.utc)).total_seconds())
                        except (TypeError, ValueError): pass
                # Stop rather than blocking beyond the bounded retry budget; caller may retry later.
                if wait > 30:
                    raise ResearchError(f'Wiki requested Retry-After {wait:g}s; sync deferred') from exc
                self.sleep(wait)
            except (error.URLError, TimeoutError, OSError) as exc:
                if attempt == 2:
                    raise ResearchError(f'Wiki connection failed: {exc}') from exc
                self.sleep(2 ** attempt)
        raise ResearchError('Wiki request exhausted retries')

    def api_get(self, **parameters):
        if parameters.get('action') not in ('query', 'parse'):
            raise ResearchError('Only read-only query and parse API actions are allowed')
        url = self.api + '?' + parse.urlencode({'format': 'json', 'formatversion': 2, **parameters})
        try:
            result = json.loads(self.get(url))
        except (ValueError, TypeError) as exc:
            raise ResearchError('Invalid wiki JSON response') from exc
        if not isinstance(result, dict) or 'error' in result:
            raise ResearchError(f'Wiki API error: {result.get("error") if isinstance(result, dict) else "invalid shape"}')
        return result


class ApprovalHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.classes = set()
        self.scripts = []
        self.in_script = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'body': self.classes = set(a.get('class', '').split())
        if tag == 'script': self.in_script = not a.get('src')

    def handle_endtag(self, tag):
        if tag == 'script': self.in_script = False

    def handle_data(self, data):
        if self.in_script: self.scripts.append(data)


def approval_from_html(html, page_id):
    parsed = ApprovalHTML()
    parsed.feed(html)
    match = re.search(r'RLCONF\s*=\s*(\{.*?\});', '\n'.join(parsed.scripts), re.S)
    if not match:
        return {'status': 'unknown', 'revision': None, 'reason': 'Page configuration marker unavailable'}
    try: config = json.loads(match.group(1))
    except ValueError:
        return {'status': 'unknown', 'revision': None, 'reason': 'Malformed page configuration'}
    if not isinstance(config,dict):
        return {'status':'unknown','revision':None,'reason':'Invalid page configuration shape'}
    if {'approvedRevs-approved','approvedRevs-noapprovedrev'} <= parsed.classes:
        return {'status':'unknown','revision':None,'reason':'Conflicting approval markers'}
    if config.get('wgArticleId') != page_id or config.get('wgAction') != 'view':
        return {'status': 'unknown', 'revision': None, 'reason': 'Page identity or view action mismatch'}
    revision = config.get('wgRevisionId')
    if 'approvedRevs-approved' in parsed.classes and type(revision) is int and revision > 0:
        return {'status': 'approved', 'revision': revision, 'reason': None}
    if 'approvedRevs-noapprovedrev' in parsed.classes:
        return {'status': 'absent', 'revision': None, 'reason': 'Wiki marks this page as having no approved revision'}
    return {'status': 'unknown', 'revision': None, 'reason': 'No verifiable approval marker'}


class WikiClient:
    def __init__(self, transport): self.transport = transport

    def info(self, title):
        data = self.transport.api_get(action='query', titles=title, redirects=1, prop='info|revisions', rvprop='ids|timestamp')
        pages = data.get('query', {}).get('pages', [])
        if len(pages) != 1: raise ResearchError('Unexpected page-query response')
        page = pages[0]
        if page.get('missing') or page.get('invalid'): raise MissingPage(title)
        if page.get('ns') != 0: raise MissingPage('Non-article namespace: ' + title)
        if not page.get('lastrevid') or not page.get('pageid'): raise ResearchError('Missing page/revision identity')
        return page

    def approval(self, page):
        stamp = now()
        url = self.transport.index + '?' + parse.urlencode({'title': page['title']})
        try:
            html = self.transport.get(url)
            state = approval_from_html(html, page['pageid'])
            state['response_sha256'] = digest(html)
        except ResearchError as exc:
            state = {'status': 'unknown', 'revision': None, 'reason': str(exc)}
        return {**state, 'checked_at': stamp, 'method': 'public-body-class-and-RLCONF', 'url': url}

    def fetch(self, title):
        for attempt in range(2):
            page = self.info(title)
            approval = self.approval(page)
            revision = approval['revision'] if approval['status'] == 'approved' else page['lastrevid']
            result = self.transport.api_get(action='parse', oldid=revision,
                prop='wikitext|text|links|sections|revid|templates|images', disableeditsection=1).get('parse', {})
            if result.get('revid') != revision or result.get('pageid') != page['pageid']:
                raise ResearchError('Parsed content does not match selected page/revision')
            if not isinstance(result.get('text'), str) or not isinstance(result.get('wikitext'), str):
                raise ResearchError('Wiki response lacks source/rendered text')
            verify = self.approval(page)
            if (verify['status'], verify['revision']) != (approval['status'], approval['revision']):
                if attempt == 0: continue
                raise ResearchError('Approval changed while fetching; no mixed snapshot stored')
            revision_data = self.transport.api_get(action='query', revids=revision, prop='revisions', rvprop='ids|timestamp')
            revision_pages = revision_data.get('query', {}).get('pages', [])
            revisions=revision_pages[0].get('revisions',[]) if len(revision_pages)==1 else []
            if (len(revision_pages) != 1 or revision_pages[0].get('pageid') != page['pageid']
                or len(revisions)!=1 or revisions[0].get('revid') != revision or not revisions[0].get('timestamp')):
                raise ResearchError('Could not verify revision timestamp/identity')
            return {'page_id': page['pageid'], 'title': result['title'], 'requested_title': title,
                    'revision': revision, 'latest_revision_at_selection': page['lastrevid'],
                    'revision_timestamp': revision_pages[0]['revisions'][0]['timestamp'],
                    'selection': 'approved' if approval['status'] == 'approved' else 'latest_fallback',
                    'approval': verify, 'fetched_at': now(), 'content': result,
                    'url': self.transport.index + '?' + parse.urlencode({'title': result['title'], 'oldid': revision})}
        raise ResearchError('Unstable revision selection')
