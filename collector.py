"""Conservative official-source CFP collection. Uncertain records never alert."""
from __future__ import annotations
import argparse, concurrent.futures, datetime as dt, email.utils, gzip, hashlib, html, http.cookiejar, io, json, os, re, time, unicodedata, urllib.error, urllib.parse, urllib.request, zlib
from html.parser import HTMLParser
from pathlib import Path
from difflib import SequenceMatcher
from copy import copy
from xml.etree import ElementTree as ET
from collections import defaultdict
import threading
from protego import Protego

ROOT=Path(__file__).resolve().parent
AGENT='CallAtlas/1.0 (+https://github.com/wdeliang978/special-issue-radar; academic CFP monitor)'
DOMAINS=('springer.com','springernature.com','nature.com','biomedcentral.com','sciencedirect.com','elsevier.com','wiley.com','sagepub.com','tandfonline.com','taylorandfrancis.com','ieee.org','computer.org','j-ets.net')
EXTRA_HOSTS=set()
SOURCE_FRESH_DAYS=8
CFP_PATH=re.compile(r'/(?:collections/[^/?#]+|calls?-for-(?:papers|submissions)/[^/?#]+|special[_-]issues/[^/?#]+|special-issue/[^/?#]+|publications/author-resources/calls-for-papers/[^/?#]+)',re.I)
INDEX_TERMS={'SSCI':r'\bSocial Sciences? Citation Index\b|\bSSCI\b','SCIE':r'\bScience Citation Index Expanded\b|\bSCIE\b'}
MONTHS={m.lower():i for i,m in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'],1)}
MONTH_PATTERN='(?:'+ '|'.join(MONTHS)+r'|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)'
DATE_RE=re.compile(r'\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}(?:st|nd|rd|th)?\s+'+MONTH_PATTERN+r'[.,]?\s+\d{4}|'+MONTH_PATTERN+r'[.]?\s+\d{1,2}(?:st|nd|rd|th)?[,]?\s+\d{4})\b',re.I)
TOPIC_PATTERNS=[('AI in Education',r'(?:\bai\b|artificial intelligence|generative).{0,90}(?:education|learning|teach)|(?:education|pedagog).{0,90}(?:\bai\b|artificial intelligence)'),('AI / NLP',r'\bAI\b|artificial intelligence|natural language processing|\bNLP\b|language models?|machine learning|deep learning'),('Explainable AI',r'explainab|interpretab.{0,25}(?:AI|model)'),('教育技术',r'education(?:al)? technolog|learning analytics|EdTech|smart learning|digital learning'),('教育学',r'education|pedagog|teaching|learning sciences'),('心理学',r'psycholog|mental health|well.?being|cogniti|adolescen'),('STEM Education',r'\bSTEM\b|science education|mathematics education'),('Language Education',r'language (?:education|learning|teaching)|English.medium|applied linguistics|literacy')]

def utcnow(): return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
def today():
    from zoneinfo import ZoneInfo
    return dt.datetime.now(ZoneInfo('America/New_York')).date().isoformat()
def read(name,default):
    p=ROOT/name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default
def write(name,data):
    target=ROOT/name; temp=target.with_suffix(target.suffix+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temp.replace(target)
def allowed(url):
    if not url:return False
    p=urllib.parse.urlsplit(url);host=(p.hostname or '').lower()
    return p.scheme=='https' and not p.username and not p.password and p.port in (None,443) and (host in EXTRA_HOSTS or any(host==d or host.endswith('.'+d) for d in DOMAINS))
def canonical(url):
    p=urllib.parse.urlsplit(url)
    query=urllib.parse.parse_qsl(p.query,keep_blank_values=True)
    cookie_error=any(k=='error' and v=='cookies_not_supported' for k,v in query) and (p.hostname or '').endswith(('springer.com','nature.com'))
    query=[(k,v) for k,v in query if not k.startswith('utm_') and k!='via' and not (cookie_error and k in ('error','code'))]
    return urllib.parse.urlunsplit((p.scheme,p.netloc,p.path.rstrip('/'),urllib.parse.urlencode(query),''))

class NavigationLinks(HTMLParser):
    def __init__(self,source):
        super().__init__(convert_charrefs=True);self.links=[];self.anchor=None;self.feed(source)
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='a' and a.get('href'):self.anchor=[a['href'],[]]
    def handle_data(self,data):
        if self.anchor:self.anchor[1].append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.anchor:self.links.append((self.anchor[0],' '.join(self.anchor[1]).strip()));self.anchor=None

class Document(HTMLParser):
    def __init__(self,source):
        super().__init__(convert_charrefs=True);self.parts=[];self.links=[];self.link_context={};self.meta={};self.stack=[];self.ignored=0;self.anchor=None;self.headings=[];self.heading=None;self.format='html';self.feed(source)
        self.text=re.sub(r'[ \t]+',' ',' '.join(self.parts));self.text=re.sub(r'\n\s*\n','\n',self.text).strip()
        self.navigation_links=NavigationLinks(source).links
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('script','style','nav','footer','noscript','svg'):self.ignored+=1
        if self.ignored:return
        if tag=='meta' and (a.get('name') or a.get('property')):self.meta[a.get('name',a.get('property'))]=a.get('content','')
        if tag in ('p','div','section','h1','h2','h3','li','br','tr','dt','dd'):self.parts.append('\n')
        if tag=='a' and a.get('href'):self.anchor=[a['href'],[]]
        if tag=='h1':self.heading=[]
    def handle_endtag(self,tag):
        if tag in ('script','style','nav','footer','noscript','svg') and self.ignored:self.ignored-=1;return
        if self.ignored:return
        if tag=='a' and self.anchor:
            self.links.append((self.anchor[0],' '.join(self.anchor[1]).strip()));self.link_context[self.anchor[0]]=' '.join(self.parts)[-700:];self.anchor=None
        if tag=='h1' and self.heading is not None:self.headings.append(' '.join(self.heading).strip());self.heading=None
        if tag in ('p','div','section','h1','h2','h3','li','tr','dt','dd'):self.parts.append('\n')
    def handle_data(self,data):
        if not self.ignored:
            self.parts.append(data)
            if self.anchor is not None:self.anchor[1].append(data)
            if self.heading is not None:self.heading.append(data)

def pdf_document(raw):
    from pypdf import PdfReader
    reader=PdfReader(io.BytesIO(raw))
    if len(reader.pages)>30:raise ValueError('PDF exceeds 30 page limit')
    doc=Document('');doc.format='pdf';doc.text='\n'.join(page.extract_text() or '' for page in reader.pages)
    return doc

def discover_candidates(source,doc,known):
    """Journal-owned document links are retained even when their host needs review."""
    out=[]
    links=list(doc.links)
    for path,label in doc.navigation_links:
        if (path,label) not in links and re.search(r'call for papers|special[ -]issue|themed issue',label,re.I):links.append((path,label))
    for path,label in links:
        url=canonical(urllib.parse.urljoin(getattr(doc,'url',source['url']),path));p=urllib.parse.urlsplit(url)
        if url in known:continue
        context=doc.link_context.get(path,label)
        is_call=bool(re.search(r'call for papers|special[ -]issue|themed issue',context,re.I))
        external_pdf=(p.scheme=='https' and p.hostname in source.get('document_hosts',[]) and bool(re.fullmatch(r'/file/d/[\w-]+/view',p.path)) and is_call and bool(relevant(label)))
        direct_pdf=allowed(url) and (p.path.lower().endswith('.pdf') or bool(re.search(r'(?:^|&)eID=dumpFile(?:&|$)',p.query))) and is_call
        named_call=source.get('journal_id') and re.search(r'call for papers|special issue[: –-]|themed issue[: –-]',label,re.I) and not re.search(r'propos|guest.editor',label,re.I)
        if (allowed(url) and (CFP_PATH.search(p.path) or named_call)) or direct_pdf or external_pdf:
            out.append({'url':url,'title':label,'publisher':source['publisher'],'journal_id':source.get('journal_id'),'discovery_source_url':source['url'],'format':'external-pdf' if external_pdf else 'pdf' if direct_pdf else 'html'})
    return out

def discover_hubs(source,doc):
    out=[]
    for path,label in doc.navigation_links:
        url=canonical(urllib.parse.urljoin(getattr(doc,'url',source['url']),path))
        if allowed(url) and url!=canonical(source['url']) and re.fullmatch(r'(?:view |see |all |open |browse )?(?:calls? for papers|special issues?(?: and collections)?|collections|journal updates|updates|announcements)(?:[ ›»↗]+)?',label,re.I):
            out.append({**source,'id':source['id']+'-hub-'+hashlib.sha256(url.encode()).hexdigest()[:8],'url':url,'parent_source_id':source['id'],'purpose':'discovery'})
    return list({h['url']:h for h in out}.values())[:3]

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not allowed(newurl):raise AccessError('redirect_domain','Redirect outside verified publisher domains: '+newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

class AccessError(ValueError):
    def __init__(self,code,message):self.code=code;super().__init__(message)

def error_code(error):
    if isinstance(error,AccessError):return error.code
    text=str(error or '')
    for pattern,code in [(r'HTTP Error (401|403)','access_denied'),(r'HTTP Error (404|410)','not_found'),(r'HTTP Error 429','rate_limited'),(r'robots.txt unavailable','robots_unavailable'),(r'robots policy','robots_disallowed'),(r'Redirect outside','redirect_domain'),(r'identity could not','identity_unconfirmed'),(r'access challenge','challenge'),(r'content too short','dynamic_content'),(r'CERTIFICATE_VERIFY_FAILED','certificate'),(r'infinite loop','redirect_loop'),(r'getaddrinfo|Name or service not known','dns'),(r'timed out|timeout|10060','timeout')]:
        if re.search(pattern,text,re.I):return code
    return 'network_error' if error else None

def decode_response(raw,headers,is_robots=False):
    """Some journal servers gzip even without Accept-Encoding; never parse bytes as text."""
    encoding=headers.get('Content-Encoding','').lower()
    if encoding=='gzip' or raw.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:raw=stream.read(4_000_001)
    elif encoding=='deflate':raw=zlib.decompressobj().decompress(raw,4_000_001)
    elif encoding and encoding!='identity':raise AccessError('content_encoding','Unsupported content encoding: '+encoding)
    if len(raw)>4_000_000:raise AccessError('document_limit','Document exceeds 4 MB limit')
    if is_robots:
        text=raw.decode('utf-8-sig',errors='replace')
        if re.search(r'<(?:!doctype|html)|_Incapsula_Resource',text,re.I):raise AccessError('robots_unavailable','robots.txt returned an HTML page instead of crawl rules')
        if not text.strip() or re.search(r'^\s*(?:user-agent|sitemap|allow|disallow)\s*:',text,re.M|re.I) or all(not line.strip() or line.lstrip().startswith('#') for line in text.splitlines()):return text
        raise AccessError('robots_unavailable','robots.txt response could not be recognized as crawl rules')
    if raw.startswith(b'%PDF'):return pdf_document(raw)
    content_type=headers.get('Content-Type','')
    if not any(t in content_type for t in ('text/','json','xml')):raise AccessError('document_type','Unsupported document type: '+content_type)
    charset=headers.get_content_charset() or 'utf-8'
    return raw.decode(charset,errors='replace')

class Fetcher:
    def __init__(self):
        self.cache={};self.robots={};self.robots_errors={};self.reports=[];self.host_slots=defaultdict(lambda:threading.Semaphore(2));self.final_urls={};self.response_meta={}
        self.host_clocks=defaultdict(threading.Lock);self.last_request={}
        self.opener=urllib.request.build_opener(SafeRedirect(),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def _get(self,url,extra_headers=None,timeout=22):
        req=urllib.request.Request(url,headers={'User-Agent':AGENT,'Accept':'text/html,application/xhtml+xml,application/pdf,application/json','Accept-Encoding':'gzip, deflate',**(extra_headers or {})})
        for attempt in range(2):
            try:
                self.wait_turn(url)
                with self.opener.open(req,timeout=timeout) as response:
                    self.final_urls[url]=response.url
                    self.response_meta[url]={key:response.headers.get(key) for key in ('X-WP-TotalPages','X-WP-Total')}
                    return decode_response(response.read(4_000_001),response.headers,is_robots=urllib.parse.urlsplit(url).path=='/robots.txt')
            except urllib.error.HTTPError as e:
                if attempt or e.code not in (502,503,504):raise
            except (TimeoutError,urllib.error.URLError) as e:
                if attempt or not re.search(r'timed out|timeout|10060',str(e),re.I):raise
            time.sleep(1)
    def wait_turn(self,url):
        p=urllib.parse.urlsplit(url);origin=p.scheme+'://'+p.netloc;robot=self.robots.get(origin)
        delay=(robot.crawl_delay('CallAtlas') or 0) if robot else 0
        rate=robot.request_rate('CallAtlas') if robot else None
        if rate and rate.requests:delay=max(delay,rate.seconds/rate.requests)
        if delay>60:raise AccessError('rate_limited','Publisher requires a crawl interval beyond this run budget')
        if delay:
            with self.host_clocks[p.hostname]:
                wait=delay-(time.monotonic()-self.last_request.get(p.hostname,0))
                if wait>0:time.sleep(wait)
                self.last_request[p.hostname]=time.monotonic()
        else:self.last_request[p.hostname]=time.monotonic()
    def check_permission(self,url):
        if not allowed(url):raise AccessError('redirect_domain','URL is outside verified publisher allowlist')
        p=urllib.parse.urlsplit(url);origin=p.scheme+'://'+p.netloc
        robot=self.robots.get(origin)
        if robot is False:raise AccessError('robots_unavailable','robots.txt unavailable; access permission could not be checked: '+self.robots_errors.get(origin,''))
        if robot and not robot.can_fetch(url,'CallAtlas'):raise AccessError('robots_disallowed','Publisher robots policy disallows this path')
    def prime_robots(self,urls):
        origins={urllib.parse.urlsplit(u).scheme+'://'+urllib.parse.urlsplit(u).netloc for u in urls if allowed(u)}-set(self.robots)
        def one(origin):
            try:
                body=self._get(origin+'/robots.txt');return origin,Protego.parse(body)
            except urllib.error.HTTPError as e:
                if e.code in (401,403,429) or e.code>=500:self.robots_errors[origin]=str(e);return origin,False
                return origin,None
            except Exception as e:self.robots_errors[origin]=str(e);return origin,False
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for origin,robot in pool.map(one,sorted(origins)):self.robots[origin]=robot
    def fetch_json(self,url,extra_headers=None):
        """Read an explicitly configured public publisher endpoint with the same access rules."""
        code=None
        try:
            self.check_permission(url)
            with self.host_slots[urllib.parse.urlsplit(url).hostname]:body=self._get(url,extra_headers,timeout=55)
            data=json.loads(body)
            if not isinstance(data,(list,dict)):raise AccessError('directory_incomplete','Unexpected publisher directory response')
            error=None
        except Exception as e:data=None;error=type(e).__name__+': '+str(e)[:180];code=error_code(e)
        self.reports.append({'url':url,'status':'ok' if data is not None else 'error','error':error,'error_code':code,'format':'publisher-json'})
        return data,self.response_meta.get(url,{}),error
    def fetch(self,url):
        url=canonical(url)
        if url in self.cache:return self.cache[url]
        failure_code=None
        try:
            self.check_permission(url)
            p=urllib.parse.urlsplit(url)
            with self.host_slots[p.hostname]:source=self._get(url)
            if isinstance(source,str) and re.search(r'_Incapsula_Resource\?|<title>\s*(?:Just a moment|Access Denied)|id=["\']challenge-form',source,re.I):raise AccessError('challenge','Publisher returned an access challenge')
            doc=source if isinstance(source,Document) else Document(source)
            doc.url=self.final_urls.get(url,url)
            if re.search(r'^(?:Access Denied|Just a moment|Robot Challenge|Forbidden)|enable JavaScript and cookies to continue|verify (?:that )?you are (?:a )?human',doc.text[:1500],re.I):raise AccessError('challenge','Publisher returned an access challenge')
            if len(doc.text)<180:raise AccessError('dynamic_content','Page content too short; JavaScript or another entry may be required')
            result=(doc,None)
        except Exception as e:failure_code=error_code(e);result=(None,type(e).__name__+': '+str(e)[:180])
        self.cache[url]=result;self.reports.append({'url':url,'final_url':self.final_urls.get(url),'status':'ok' if result[0] else 'error','error':result[1],'error_code':failure_code});return result

def parse_date(text):
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',text):return dt.date.fromisoformat(text).isoformat()
        clean=re.sub(r'(\d)(st|nd|rd|th)\b',r'\1',text,flags=re.I).replace(',','').replace('.','')
        parts=clean.split();month=next((p for p in parts if p.isalpha()),'').lower()
        number=next((n for m,n in MONTHS.items() if m==month or m.startswith(month[:3])),None)
        nums=[int(p) for p in parts if p.isdigit()];year=next(n for n in nums if n>31);day=next(n for n in nums if n<=31)
        return dt.date(year,number,day).isoformat()
    except (ValueError,TypeError,StopIteration):return None

def submission_windows(text):
    pattern=r'(?:full (?:manuscript|paper)s?|special issue) submissions?\s+(?:(?:to )?occur\s+)?between\s+('+DATE_RE.pattern+r')\s+and\s+('+DATE_RE.pattern+r')'
    return [(parse_date(m[1]),parse_date(m[2])) for m in re.finditer(pattern,text,re.I)]

def submission_document(url,doc):
    host=urllib.parse.urlsplit(url).hostname or ''
    if (host=='aom.org' or host.endswith('.aom.org')) and '/event/' in urllib.parse.urlsplit(url).path:
        doc=copy(doc)
        # AOM appends other journals' events, including their own deadlines.
        doc.text=re.split(r'\n\s*(?:Add to calendar|Upcoming Events)\s*\n',doc.text,maxsplit=1,flags=re.I)[0]
    return doc

def extract_dates(text):
    text=re.sub(r'(\d)\s+(st|nd|rd|th)\b',r'\1\2',text.replace('\r','\n').replace('\xa0',' '),flags=re.I)
    found={'abstract':set(),'full':set()}
    # Only attach a date to an explicit deadline label, never publication/opening dates.
    patterns={
      'abstract':r'(?:abstracts?(?: submissions?)?(?:\s*\([^)]{0,60}\))?\s*(?:are\s+)?(?:deadline|due|by)|(?:deadline|due date)\s*(?:for|of)?\s*(?:the )?(?:submission of )?(?:extended )?abstracts?|(?:submission of )?abstracts?\s*:)',
      'full':r'(?:(?:full[ -]?(?:paper|manuscript)s?|manuscripts?|papers?|submissions?)(?: submission)?\s*(?:deadline|due|by)|(?:deadline|due date)\s*(?:for|of)?\s*(?:full[ -]?)?(?:paper|manuscript|submission)s?|submission deadline\s*:)' }
    abstract_labels=[m.span() for m in re.finditer(patterns['abstract'],text,re.I)]
    for kind,pat in patterns.items():
        for match in re.finditer(pat,text,re.I):
            if kind=='full' and any(a<match.end() and b>match.start() for a,b in abstract_labels):continue
            # CFP timetables also list revision and camera-ready dates. These are
            # not first-submission deadlines, including in single-line PDF text.
            before=text[max(0,match.start()-45):match.start()]
            if re.search(r'(?:revis(?:ion|ed)|camera[ -]?ready|proof|editorial)\s+(?:\w+\s+){0,3}$',before,re.I):continue
            if re.search(r'(?:feedback|notification|invitation)\s+(?:\w+\s+){0,8}$',before,re.I):continue
            if kind=='abstract' and re.search(r'(?:accepted|acceptance of|announcement of|notification of)\s*$',before,re.I):continue
            snippet=text[match.end():match.end()+100]
            if kind=='full' and re.match(r'\s*(?:(?:of|for)\s+)?(?:abstracts?|revised|final version)\b',snippet,re.I):continue
            # Do not take the following timetable row's date when this row has
            # its own date before the label. A date-only next line is allowed.
            line=snippet.split('\n',1)[0]
            if line.strip():snippet=line
            else:
                prefix=text[:match.start()].rsplit('\n',1)[-1]
                snippet='' if DATE_RE.search(prefix) else snippet.lstrip().split('\n',1)[0]
            stop=re.search(r'\b(?:publication|notification|revis(?:ion|ed)|abstract|submission opens?)\b',snippet,re.I)
            if stop:snippet=snippet[:stop.start()]
            dates=DATE_RE.findall(snippet)
            if dates:
                d=parse_date(dates[0])
                if d:found[kind].add(d)
    # Publisher timetables often put the date before the stage label.
    for m in DATE_RE.finditer(text):
        tail=text[m.end():m.end()+150].split('\n')[0]
        if re.match(r'\s*[:–—-]\s*(?:(?:extended )?abstracts?(?: submissions?)?\s+(?:submitted|due|deadline)|submission of (?:extended )?abstracts?|deadline for (?:submission of )?(?:extended )?abstracts?)',tail,re.I):found['abstract'].add(parse_date(m.group()))
        if re.match(r'\s*[:–—-]\s*(?:full (?:papers?|manuscripts?|articles?)(?: submissions?)?\s+(?:submitted|due|deadline)|submission of (?:full (?:papers?|manuscripts?)|first draft)|deadline for (?:submission of )?full (?:papers?|manuscripts?))',tail,re.I):found['full'].add(parse_date(m.group()))
    for m in re.finditer(r'submit\s+(?:(?:an?|your)\s+)?(?:single\s+)?(?:extended\s+)?abstracts?\b',text,re.I):
        due=re.search(r'\b(?:by|before)\s+('+DATE_RE.pattern+')',text[m.end():m.end()+350].split('\n',1)[0],re.I)
        if due:found['abstract'].add(parse_date(due[1]))
    for line in text.splitlines():
        if re.search(r'abstracts?[^\n]{0,120}(?:submitted|sent|emailed)',line,re.I):
            due=re.search(r'\b(?:by|before)\s+(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+)?('+DATE_RE.pattern+')',line,re.I)
            if due:found['abstract'].add(parse_date(due[1]))
    for dates in found.values():dates.discard(None)
    for _,deadline in submission_windows(text):
        if deadline:found['full'].add(deadline)
    return {k:sorted(v) for k,v in found.items()}

def abstract_stage(text):
    return bool(re.search(r'abstract[ -]first|call for (?:extended )?abstract|abstract submissions? (?:open|clos)|full (?:paper|manuscript) invitations|abstracts?[\s\S]{0,350}invited to submit (?:a )?full|submission of (?:extended )?abstract',text,re.I))

def relevant(text):
    tags=[name for name,pat in TOPIC_PATTERNS if re.search(pat,text,re.I)]
    if re.search(r'digital competenc|technology[ -]enhanced|adaptive teach',text,re.I) and '教育技术' not in tags:tags.append('教育技术')
    return tags
def eligible(r,asof):
    if r.get('indexing_verified') is not True or not any(i in ('SSCI','SCIE') for i in r.get('indexing',[])):return False
    if r.get('indexing_evidence_type')=='user_jcr':
        proof=r.get('indexing_provenance') or {}
        try:age=(dt.date.fromisoformat(asof)-dt.date.fromisoformat(proof.get('period','')+'-01')).days
        except ValueError:return False
        editions={ref.get('edition') for ref in proof.get('rows',[]) if ref.get('sheet') and isinstance(ref.get('row'),int) and ref['row']>=2}
        return proof.get('kind')=='user_jcr' and bool(proof.get('file')) and set(r['indexing'])<=editions and 0<=age<=365
    try:age=(dt.date.fromisoformat(asof)-dt.date.fromisoformat(r.get('indexing_checked_at',''))).days
    except ValueError:return False
    return bool(r.get('indexing_evidence_url')) and 0<=age<=90
def open_call(r,asof):
    if r.get('review_required') or r.get('status')=='closed':return False
    if r.get('full_paper_deadline') and r['full_paper_deadline']<asof:return False
    if r.get('abstract_required') is not False and r.get('abstract_deadline') and r['abstract_deadline']<asof:return False
    return any(r.get(k,'') and r[k]>=asof for k in ('abstract_deadline','full_paper_deadline')) or r.get('status')=='rolling'
def notifiable(r,asof):
    try:fresh=0<=(dt.date.fromisoformat(asof)-dt.date.fromisoformat(r.get('checked_at',''))).days<=SOURCE_FRESH_DAYS
    except ValueError:return False
    return eligible(r,asof) and open_call(r,asof) and fresh

def journal_identity(j,text):
    normalize=lambda s:re.sub(r'\W+',' ',''.join(c for c in unicodedata.normalize('NFKD',s.casefold().replace('&',' and ')) if not unicodedata.combining(c))).strip()
    normalized=normalize(text)
    return any((' '+normalize(name)+' ') in (' '+normalized+' ') for name in [j['name']]+j.get('aliases',[]) if name) or any(issn in text for issn in j.get('issns',[])) or any(re.search(r'(?<!\w)'+re.escape(alias)+r'(?!\w)',text[:500],re.I) for alias in j.get('identity_aliases',[]))

def destination_journals(url,doc,journals,context):
    normalize=lambda s:re.sub(r'\W+',' ',s.casefold().replace('&',' and ')).strip()
    participant=re.search(r'Participating journal\s*:\s*([^\n]+)',doc.text,re.I)
    if participant:
        return [j for j in journals if any(normalize(name)==normalize(participant[1]) for name in [j['name']]+j.get('aliases',[]))]
    # AOM event pages link other AOM journals in shared surrounding content.
    # The explicit journal acronym in an event URL must agree with the registry.
    aom=re.search(r'/event/([a-z]+)-call-for-',urllib.parse.urlsplit(url).path,re.I) if (urllib.parse.urlsplit(url).hostname or '').endswith('aom.org') else None
    if aom:return [j for j in journals if j.get('publisher_journal_code')==aom[1].lower()]
    linked={canonical(urllib.parse.urljoin(url,path)) for path,_ in doc.links}
    destinations=[j for j in journals if j.get('journal_url') and canonical(j['journal_url']) in linked]
    if destinations:return destinations
    lines={normalize(line) for line in doc.text.splitlines() if line.strip()}
    matches=[j for j in journals if journal_identity(j,doc.text) and (len(j['name'].split())>2 or normalize(j['name']) in lines or any(i in doc.text for i in j.get('issns',[])))]
    bound=next((j for j in matches if j.get('id')==context.get('journal_id')),None)
    if bound and journal_identity(bound,doc.text[:2500]):return [bound]
    return matches

def index_fields(j):
    return {'indexing':j['indexing'],'indexing_verified':j['verified'],'indexing_checked_at':j['checked_at'],'indexing_evidence_url':j.get('evidence_url'),'indexing_evidence_type':j.get('evidence_type','official'),'indexing_provenance':j.get('registry_provenance') if j.get('evidence_type')=='user_jcr' else None}

def evidence_text(r):
    if r.get('indexing_evidence_type')=='user_jcr':
        p=r.get('indexing_provenance') or {}
        refs='; '.join(f"{v['sheet']}!G{v['row']}" for v in p.get('rows',[]))
        return f"用户提供的 JCR 清单（{p.get('period','')}）；{p.get('file','')}；{refs}。此项为清单核对，不表示官网实时核验。"
    return r.get('indexing_evidence_url') or '索引证据待核验'

def update_index(j,doc,asof,evidence_url=None):
    if not doc:return
    text=doc.text
    # Scope to a single journal evidence page with its exact name or verified ISSN.
    identity=journal_identity(j,text)
    # On imported homepages, a claim in an editor biography or a cited article
    # is not evidence for this journal. Restrict promotion to the index section.
    section=re.search(r'(?:abstract(?:ed|ing)?\s*(?:and|&|/)\s*index(?:ed|ing)?|indexed in|indexing information)[\s\S]{0,4500}',text,re.I)
    evidence=section.group(0) if section else text if not j.get('registry_provenance') else ''
    found=[i for i,pat in INDEX_TERMS.items() if re.search(pat,evidence,re.I)]
    if identity and found:j.update(indexing=found,verified=True,checked_at=asof,evidence_type='official',evidence_url=evidence_url or j.get('evidence_url'))
    elif identity and re.search(r'Emerging Sources Citation Index|\bESCI\b',evidence,re.I):j.update(indexing=['ESCI'],verified=False,checked_at=asof,evidence_type='official',evidence_url=evidence_url or j.get('evidence_url'))

def refresh_record(r,j,doc,asof):
    r.update(index_fields(j))
    if not doc:return
    doc=submission_document(r.get('cfp_url',''),doc)
    normalized=lambda s:re.sub(r'\W+',' ',s).strip().casefold()
    title_matches=normalized(r['title']) in normalized(doc.text) or any(SequenceMatcher(None,normalized(r['title']),normalized(h)).ratio()>.88 for h in doc.headings)
    if not title_matches:return
    if getattr(doc,'verification_url',None):r['verification_url']=doc.verification_url
    if re.search(r'closed for submissions|submissions? (?:are |is )?closed|no longer accepting (?:submissions|manuscripts)',doc.text,re.I):r.update(status='closed',checked_at=asof);return
    parsed=extract_dates(doc.text)
    extra_dates=[parse_date(v) for v in getattr(doc,'additional_deadlines',[])]
    existing_dates=[r[k] for k in ('abstract_deadline','full_paper_deadline') if r.get(k)]
    # An unchanged API date may corroborate a previously verified stage. New
    # records still need an explicit stage label; never guess from field order.
    if any(d is None or d not in parsed['abstract']+parsed['full']+existing_dates for d in extra_dates):r['review_required']=True;return
    if any(len(v)>1 for v in parsed.values()) or (abstract_stage(doc.text) and not parsed['abstract'] and not r.get('abstract_deadline')):
        r['review_required']=True;return
    if parsed['abstract'] and r.get('abstract_deadline') not in parsed['abstract']:
        r['review_required']=True;return
    visible_dates={parse_date(s) for s in DATE_RE.findall(doc.text)}|set(extra_dates)
    # Keep human-reviewed details if their exact dates remain present.
    if existing_dates and all(d in visible_dates for d in existing_dates):r['checked_at']=asof;return
    updates={}
    for kind,key in [('abstract','abstract_deadline'),('full','full_paper_deadline')]:
        values=parsed[kind]
        if len(values)>1:r['review_required']=True;return
        if len(values)==1:updates[key]=values[0]
        elif r.get(key) and r[key] not in visible_dates:r['review_required']=True;return
    if updates:r.update(updates);r.update(checked_at=asof,review_required=False)

def discover_record(url,doc,journals,asof,context=None):
    context=context or {}
    doc=submission_document(url,doc)
    if re.search(r'closed for submissions|submissions? (?:are |is )?closed|no longer accepting (?:submissions|manuscripts)',doc.text,re.I):return None,'official call is closed'
    title=(doc.headings[0] if doc.headings else doc.meta.get('og:title','')).strip()
    linked_title=context.get('title','').strip()
    normalized=lambda s:re.sub(r'\W+',' ',s).casefold().strip()
    # Elsevier uses the journal name as h1 and the CFP title as h3. The link
    # on its journal CFP page identifies the title, but must occur in the page.
    if len(linked_title)>15 and normalized(linked_title) in normalized(doc.text):title=linked_title
    if not title or len(title)<10 or re.search(r'guest editor|propos(?:e|als?).{0,30}special issue',title,re.I):return None,'not a manuscript call'
    matches=destination_journals(url,doc,journals,context)
    if len(matches)!=1:return None,'journal identity not unambiguous or not in verified registry'
    if re.search(r'Multiple participating journals',doc.text,re.I):return None,'multi-journal collection requires specific destination review'
    if re.search(r'pre[ -](?:submission evaluation|screening process)|invited (?:full )?manuscripts',doc.text,re.I):return None,'invitation or pre-screening stage requires deadline review'
    j=matches[0]
    if normalized(title)==normalized(j['name']) or re.fullmatch(r'(?:special issues?|calls? for papers|collections)(?:\s*[|–-].*)?',title,re.I):return None,'specific special-issue title needs review'
    # Titles and journal scope prevent keywords in editors' bios or article lists from
    # turning an unrelated humanities collection into an AI/education opportunity.
    tags=relevant(title)
    scope_tags=relevant(j['name'])+j.get('scope_topics',[])
    tags=list(dict.fromkeys(tags+[t for t in scope_tags if t in ('心理学','教育学','STEM Education','教育技术','Language Education')]))
    if not tags:return None,'research relevance needs review'
    parsed=extract_dates(doc.text)
    extra_dates=[parse_date(v) for v in getattr(doc,'additional_deadlines',[])]
    if any(d is None or d not in parsed['abstract']+parsed['full'] for d in extra_dates):return None,'additional publisher deadline requires submission-stage review'
    if any(len(v)>1 for v in parsed.values()):return None,'multiple conflicting stage deadlines'
    abstract=next(iter(parsed['abstract']),None);full=next(iter(parsed['full']),None)
    if re.search(r'abstract submissions? (?:are )?closed',doc.text,re.I) or (abstract_stage(doc.text) and not abstract):return None,'abstract prerequisite deadline requires review'
    if not full:return None,'no unambiguous full manuscript deadline'
    required=None
    if abstract:
        if re.search(r'(?:optional|not required).{0,70}abstract|abstract.{0,70}(?:optional|not required)|without (?:previous )?submission of an? abstract',doc.text,re.I):required=False
        elif re.search(r'(?:must|required|invited).{0,70}abstract|abstract.{0,70}(?:must|required|invited)',doc.text,re.I):required=True
        if re.search(r'abstract[ -]first|abstracts?[\s\S]{0,350}invited to submit (?:a )?full',doc.text,re.I):required=True
        # A future, dated abstract stage can be displayed with an unknown
        # requirement; after it passes, open_call pauses recommendations.
    r={'id':'auto-'+hashlib.sha256((canonical(url)+j['id']).encode()).hexdigest()[:16],'title':title,'journal':j['name'],'journal_id':j['id'],'publisher':j['publisher'],'cfp_url':url,'abstract_deadline':abstract,'abstract_required':required,'full_paper_deadline':full,'deadline_notes_zh':'自动识别的官方征稿。请在投稿前查看原文中关于格式、资格及截止时区的要求。','topics':tags,'keywords':tags,'summary_zh':'新发现的官方专题征稿。点击查看官方页面了解完整研究范围与投稿要求。','indexing':j['indexing'],'indexing_verified':j['verified'],'indexing_evidence_url':j['evidence_url'],'indexing_checked_at':j['checked_at'],'status':'open','checked_at':asof,'first_seen':asof,'review_required':False}
    r['discovery_source_url']=context.get('discovery_source_url');r['source_format']=doc.format
    if getattr(doc,'verification_url',None):r['verification_url']=doc.verification_url
    opening=re.search(r'Submissions? open(?:s)?\s+(?:on\s+|from\s+)?('+DATE_RE.pattern+')',doc.text,re.I)
    if opening:r['submission_opens']=parse_date(opening[1])
    windows=submission_windows(doc.text)
    if len(windows)==1 and windows[0][1]==full:r['submission_opens']=windows[0][0]
    r.update(index_fields(j))
    return (r,None) if notifiable(r,asof) else (None,'not open or index not verified')

def coverage(journals,sources):
    return [{**{k:j.get(k) for k in ('id','name','publisher','issns','indexing','verified','checked_at','journal_url','evidence_type','registry_provenance','directory_status')},'source_ids':[s['id'] for s in sources if s.get('journal_id')==j['id']]} for j in journals]

def record_identity(r):
    title=re.sub(r'^(?:(?:call for papers|special issue|collection)\s*[:–—-]\s*)+','',r['title'],flags=re.I)
    return r['journal_id']+'|'+re.sub(r'\W+',' ',title.casefold()).strip()

def candidate_batch(candidates,previous,limit):
    """Oldest checks first, one link per journal per round, with persistent history."""
    history={c['url']:c for c in previous}
    groups=defaultdict(list)
    for c in candidates.values():
        old=history.get(c['url'],{})
        groups[c.get('journal_id') or c['publisher']].append({**c,'discovered_at':old.get('discovered_at'),'last_checked':old.get('last_checked')})
    for group in groups.values():group.sort(key=lambda c:(c.get('last_checked') or '',c['url']))
    result=[]
    while groups and len(result)<limit:
        for key in sorted(groups,key=lambda k:(groups[k][0].get('last_checked') or '',k)):
            result.append(groups[key].pop(0))
            if not groups[key]:del groups[key]
            if len(result)>=limit:break
    return result

def rss(catalog,base_url,asof):
    ET.register_namespace('atom','http://www.w3.org/2005/Atom')
    root=ET.Element('rss',version='2.0');channel=ET.SubElement(root,'channel')
    for tag,value in [('title','Call Atlas · SSCI / SCIE 征稿'),('link',base_url),('description','AI、教育与心理学专题征稿。仅包含当前通过核验的 SSCI / SCIE 期刊。'),('language','zh-cn'),('lastBuildDate',email.utils.format_datetime(dt.datetime.now(dt.timezone.utc)))]:ET.SubElement(channel,tag).text=value
    ET.SubElement(channel,'{http://www.w3.org/2005/Atom}link',href=base_url+'feed.xml',rel='self',type='application/rss+xml')
    for r in sorted(catalog['records'],key=lambda x:x.get('first_seen',''),reverse=True):
        if not notifiable(r,asof):continue
        item=ET.SubElement(channel,'item');ET.SubElement(item,'title').text=r['title']+' — '+r['journal'];ET.SubElement(item,'link').text=r['cfp_url'];ET.SubElement(item,'guid',isPermaLink='false').text=r['id']
        stamp=dt.datetime.fromisoformat(r.get('first_seen',asof)).replace(tzinfo=dt.timezone.utc);ET.SubElement(item,'pubDate').text=email.utils.format_datetime(stamp)
        desc=f"{r.get('summary_zh','')}\n摘要截止：{r.get('abstract_deadline') or '未单独公布'}\n全文截止：{r.get('full_paper_deadline') or '未公布'}\n收录：{' / '.join(r['indexing'])}\n收录依据：{evidence_text(r)}\n最近征稿核验：{r.get('checked_at')}"
        ET.SubElement(item,'description').text=desc
    ET.indent(root);ET.ElementTree(root).write(ROOT/'feed.xml',encoding='utf-8',xml_declaration=True)

def event_key(r,event):return hashlib.sha256((r['id']+'|'+event).encode()).hexdigest()[:24]
def events(catalog,previous,asof):
    out=[];prior={r['id']:r for r in previous.get('records',[])}
    for r in catalog['records']:
        if not notifiable(r,asof):continue
        old=prior.get(r['id'])
        # Initial baseline is included once so the owner can subscribe to real alerts.
        out.append((event_key(r,'new'),'新增征稿',r))
        if old:
            for key in ('abstract_deadline','full_paper_deadline'):
                if old.get(key)!=r.get(key):out.append((event_key(r,key+str(r.get(key))),'截止日期变更',r))
        for key in ('abstract_deadline','full_paper_deadline'):
            if not r.get(key):continue
            days=(dt.date.fromisoformat(r[key])-dt.date.fromisoformat(asof)).days
            thresholds=[n for n in (30,14,7) if 0<=days<=n]
            if thresholds:out.append((event_key(r,key+r[key]+str(min(thresholds))),('摘要' if key=='abstract_deadline' else '全文')+f' {days} 天后截止',r))
    return out

def notify(catalog,previous,asof):
    token=os.environ.get('GITHUB_TOKEN');repo=os.environ.get('GITHUB_REPOSITORY')
    if not token or not repo:raise RuntimeError('GitHub notification credentials unavailable; delivery was not attempted')
    def api(path,data=None):
        payload=json.dumps(data).encode() if data is not None else None
        request=urllib.request.Request('https://api.github.com/repos/'+repo+path,data=payload,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':AGENT,'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=25) as response:return json.load(response)
    state=read('notification-state.json',{'sent':[]});sent=set(state['sent'])
    combined={e[0]:e for e in state.get('pending',[])}
    combined.update({e[0]:e for e in events(catalog,previous,asof)})
    current={r['id']:r for r in catalog['records']}
    pending=[(key,label,current[r['id']]) for key,label,r in combined.values() if key not in sent and r['id'] in current and notifiable(current[r['id']],asof)]
    # Save the outbox before any API call so a failed delivery cannot lose a deadline change.
    write('notification-state.json',{'sent':sorted(sent),'pending':pending,'last_success':state.get('last_success')})
    if not pending:return 0
    # Per-event markers permit crash recovery after a successful issue POST.
    for page in range(1,11):
        issues=api(f'/issues?state=all&per_page=100&page={page}')
        for issue in issues:
            sent.update(re.findall(r'call-atlas-event:([a-f0-9]{24})',issue.get('body') or ''))
        if len(issues)<100:break
    pending=[e for e in pending if e[0] not in sent]
    if pending:
        unique={r['id']:r for _,_,r in pending};lines=[f'@{repo.split("/")[0]} 本次检查有 **{len(unique)}** 条符合 SSCI / SCIE 规则的征稿更新。','',f'[打开征稿雷达](https://{repo.split("/")[0]}.github.io/{repo.split("/")[1]}/)','']
        for rid,r in unique.items():
            reasons=sorted({label for _,label,record in pending if record['id']==rid})
            lines.extend([f'### [{r["title"]}]({r["cfp_url"]})',f'{r["journal"]} · {" / ".join(r["indexing"])} · {"；".join(reasons)}',f'- 摘要：{r.get("abstract_deadline") or "未单独公布"}{"（可选）" if r.get("abstract_required") is False else ""}',f'- 全文：{r.get("full_paper_deadline") or "未公布"}',f'- 收录依据：{evidence_text(r)}', ''])
        lines.extend(f'<!-- call-atlas-event:{key} -->' for key,_,_ in pending)
        api('/issues',{'title':f'[征稿雷达] {asof} · {len(unique)} 条征稿更新','body':'\n'.join(lines)})
        sent.update(key for key,_,_ in pending)
    write('notification-state.json',{'sent':sorted(sent),'pending':[],'last_success':utcnow()})
    return len(pending)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--offline',action='store_true');parser.add_argument('--notify',action='store_true');parser.add_argument('--max-candidates',type=int,default=400);parser.add_argument('--audit-dir');args=parser.parse_args();asof=today()
    audit_dir=Path(args.audit_dir) if args.audit_dir else None
    if audit_dir:audit_dir.mkdir(parents=True,exist_ok=True)
    catalog=read('data.json',{'records':[]});previous=json.loads(json.dumps(catalog));registry=read('journals.json',{'journals':[]});journals=registry['journals'];config=read('sources.json',{'sources':[]});sources=config['sources'];queue=read('review-queue.json',{'candidates':[]})
    EXTRA_HOSTS.update(config.get('allowed_hosts',[]))
    byid={j['id']:j for j in journals}
    if not args.offline:
        fetcher=Fetcher();index_urls={j['id']:j.get('evidence_url') or j.get('evidence_candidate_url') or j.get('journal_url') for j in journals}
        known={canonical(u) for r in catalog['records'] for u in [r['cfp_url']]+r.get('alternate_cfp_urls',[])}
        directory_reports=[];directory_candidates=[]
        if config.get('publisher_directories',{}).get('taylor_francis'):
            from publisher_directories import collect_taylor_francis
            print('Reading the official Taylor & Francis CFP directory, respecting its crawl interval.',flush=True)
            report,items,documents=collect_taylor_francis(fetcher,journals,known)
            if audit_dir:(audit_dir/'publisher-documents.json').write_text(json.dumps({url:{'text':doc.text,'headings':doc.headings,'links':doc.links,'format':doc.format,'additional_deadlines':doc.additional_deadlines,'verification_url':doc.verification_url} for url,doc in documents.items()},ensure_ascii=False,indent=2),encoding='utf-8')
            directory_reports.append(report);directory_candidates.extend(items)
            for url,doc in documents.items():fetcher.cache[canonical(url)]=(doc,None)
            print(f'Publisher directory: {report["items"]} entries; complete={report["complete"]}; {len(items)} registered-journal candidates.',flush=True)
        urls=[u for u in index_urls.values() if u]+[r['cfp_url'] for r in catalog['records']]+[s['url'] for s in sources]
        print(f'Checking {len(journals)} registered journals, {len(set(urls))} configured pages.',flush=True)
        fetcher.prime_robots(urls)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for n,_ in enumerate(pool.map(fetcher.fetch,sorted(set(urls))),1):
                if n%100==0:print(f'Checked {n} configured pages.',flush=True)
        for j in journals:
            url=index_urls[j['id']]
            if url:update_index(j,fetcher.fetch(url)[0],asof,url)
        for r in catalog['records']:
            if r.get('journal_id') in byid:refresh_record(r,byid[r['journal_id']],fetcher.fetch(r['cfp_url'])[0],asof)
        candidates={c['url']:c for c in directory_candidates};reports=[]
        # Follow a single level of explicitly linked CFP hubs, never an entire site.
        hubs=[];seen={canonical(s['url']) for s in sources}
        for s in sources:
            doc,_=fetcher.fetch(s['url'])
            if doc and (not s.get('journal_id') or journal_identity(byid[s['journal_id']],doc.text)):
                for hub in discover_hubs(s,doc):
                    if hub['url'] not in seen:hubs.append(hub);seen.add(hub['url'])
        fetcher.prime_robots([s['url'] for s in hubs])
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(fetcher.fetch,[s['url'] for s in hubs]))
        all_sources=sources+hubs
        page_reports={r['url']:r for r in fetcher.reports}
        for s in all_sources:
            doc,error=fetcher.fetch(s['url']);links=[]
            if doc and s.get('journal_id') and not journal_identity(byid[s['journal_id']],doc.text):
                error='Page read, but the registered journal identity could not be confirmed';doc=None
            if doc:
                for candidate in discover_candidates(s,doc,known):
                    links.append(candidate['url']);candidates.setdefault(candidate['url'],candidate)
            page_report=page_reports.get(canonical(s['url']),{})
            reports.append({'id':s['id'],'journal_id':s.get('journal_id'),'url':s['url'],'purpose':s.get('purpose','discovery'),'final_url':page_report.get('final_url'),'status':'ok' if doc else 'error','candidates':len(set(links)),'error':error,'error_code':None if doc else 'identity_unconfirmed' if error and 'identity could not' in error else page_report.get('error_code') or error_code(error)})
        # A source outage must not erase previously discovered candidates.
        history={c['url']:c for c in queue['candidates'] if c['url'] not in known}
        for url,c in history.items():candidates.setdefault(url,c)
        candidate_list=candidate_batch(candidates,queue['candidates'],args.max_candidates)
        print(f'Checking {len(candidate_list)} CFP candidates; {len(candidates)-len(candidate_list)} deferred.',flush=True)
        fetcher.prime_robots([c['url'] for c in candidate_list])
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for n,_ in enumerate(pool.map(fetcher.fetch,[c['url'] for c in candidate_list if c.get('format')!='external-pdf']),1):
                if n%100==0:print(f'Checked {n} CFP candidate pages.',flush=True)
        reviewed={u:{**c,'discovered_at':c.get('discovered_at') or asof,'reason':c.get('reason') or 'Deferred by weekly page budget'} for u,c in candidates.items()}
        identities={record_identity(r):r for r in catalog['records']}
        for c in candidate_list:
            c.update(discovered_at=c.get('discovered_at') or asof,last_checked=asof)
            if c.get('format')=='external-pdf':
                reviewed[c['url']]={**c,'reason':'Official journal links an external PDF; deadline verification requires a permitted document source.'};continue
            doc,error=fetcher.fetch(c['url']);r,reason=discover_record(c['url'],doc,journals,asof,c) if doc else (None,error)
            if r:
                if audit_dir:(audit_dir/(r['id']+'.json')).write_text(json.dumps({'record':r,'text':doc.text,'links':doc.links,'context':c},ensure_ascii=False,indent=2),encoding='utf-8')
                identity=record_identity(r)
                if identity in identities:
                    aliases=identities[identity].setdefault('alternate_cfp_urls',[])
                    if c['url'] not in aliases:aliases.append(c['url'])
                else:catalog['records'].append(r);identities[identity]=r
                reviewed.pop(c['url'],None)
            else:reviewed[c['url']]={**c,'reason':reason}
        queue['candidates']=list(reviewed.values());queue['unchecked_due_to_limit']=max(0,len(candidates)-len(candidate_list));write('review-queue.json',queue)
        succeeded=sum(r['status']=='ok' for r in fetcher.reports);failed=len(fetcher.reports)-succeeded
        catalog['monitor']={'last_run':utcnow(),'succeeded':succeeded,'failed':failed,'sources':reports,'directories':directory_reports,'review_candidates':len(reviewed),'deferred_candidates':queue['unchecked_due_to_limit'],'pages':fetcher.reports}
        catalog['updated_at']=utcnow();write('journals.json',registry)
    base='https://wdeliang978.github.io/special-issue-radar/'
    catalog['journal_coverage']=coverage(journals,sources)
    catalog['sources']=sources;catalog['registry_import']=registry.get('import_summary');catalog['schedule']={'frequency':'weekly','day':'Monday','time_utc':'13:17','source_fresh_days':SOURCE_FRESH_DAYS}
    for r in catalog['records']:
        if r.get('journal_id') in byid:r.update(index_fields(byid[r['journal_id']]))
    rss(catalog,base,asof);write('data.json',catalog)
    if args.notify:
        delivered=notify(catalog,previous,asof);print(f'{delivered} notification events delivered or recovered.')
    print(f'{len(catalog["records"])} records; {sum(notifiable(r,asof) for r in catalog["records"])} currently eligible for alerts.')
    if not args.offline:print(f'Official pages read: {catalog["monitor"]["succeeded"]}; unavailable: {catalog["monitor"]["failed"]}.')

if __name__=='__main__':main()
