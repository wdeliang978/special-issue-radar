"""Conservative official-source CFP collection. Uncertain records never alert."""
from __future__ import annotations
import argparse, concurrent.futures, datetime as dt, email.utils, hashlib, html, json, os, re, time, urllib.error, urllib.parse, urllib.request, urllib.robotparser
from html.parser import HTMLParser
from pathlib import Path
from difflib import SequenceMatcher
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parent
AGENT='CallAtlas/1.0 (+https://github.com/wdeliang978/special-issue-radar; academic CFP monitor)'
DOMAINS=('springer.com','springernature.com','nature.com','biomedcentral.com','sciencedirect.com','elsevier.com','wiley.com','sagepub.com','tandfonline.com','taylorandfrancis.com','ieee.org','computer.org')
CFP_PATH=re.compile(r'/(?:collections/[^/?#]+|calls?-for-papers/[^/?#]+|special[_-]issues/[^/?#]+|special-issue/[^/?#]+|publications/author-resources/calls-for-papers/[^/?#]+)',re.I)
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
    p=urllib.parse.urlsplit(url);host=(p.hostname or '').lower()
    return p.scheme=='https' and not p.username and not p.password and p.port in (None,443) and any(host==d or host.endswith('.'+d) for d in DOMAINS)
def canonical(url):
    p=urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((p.scheme,p.netloc,p.path.rstrip('/'),p.query if not p.query.startswith(('utm_','via=')) else '', ''))

class Document(HTMLParser):
    def __init__(self,source):
        super().__init__(convert_charrefs=True);self.parts=[];self.links=[];self.meta={};self.stack=[];self.ignored=0;self.anchor=None;self.headings=[];self.heading=None;self.feed(source)
        self.text=re.sub(r'[ \t]+',' ',' '.join(self.parts));self.text=re.sub(r'\n\s*\n','\n',self.text).strip()
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
        if tag=='a' and self.anchor:self.links.append((self.anchor[0],' '.join(self.anchor[1]).strip()));self.anchor=None
        if tag=='h1' and self.heading is not None:self.headings.append(' '.join(self.heading).strip());self.heading=None
        if tag in ('p','div','section','h1','h2','h3','li','tr','dt','dd'):self.parts.append('\n')
    def handle_data(self,data):
        if not self.ignored:
            self.parts.append(data)
            if self.anchor is not None:self.anchor[1].append(data)
            if self.heading is not None:self.heading.append(data)

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not allowed(newurl):raise ValueError('Redirect outside official publisher domains')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

class Fetcher:
    def __init__(self): self.cache={};self.robots={};self.reports=[]
    def _get(self,url):
        req=urllib.request.Request(url,headers={'User-Agent':AGENT,'Accept':'text/html,application/xhtml+xml'})
        with urllib.request.build_opener(SafeRedirect()).open(req,timeout=22) as response:
            if 'text/' not in response.headers.get('Content-Type',''):raise ValueError('Unsupported non-HTML document')
            raw=response.read(4_000_001)
            if len(raw)>4_000_000:raise ValueError('Document exceeds 4 MB limit')
            return raw.decode(response.headers.get_content_charset() or 'utf-8',errors='replace')
    def prime_robots(self,urls):
        origins={urllib.parse.urlsplit(u).scheme+'://'+urllib.parse.urlsplit(u).netloc for u in urls if allowed(u)}
        def one(origin):
            try:
                body=self._get(origin+'/robots.txt');robot=urllib.robotparser.RobotFileParser();robot.parse(body.splitlines());return origin,robot
            except urllib.error.HTTPError as e:return origin,False if e.code in (401,403) else None
            except Exception:return origin,None
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for origin,robot in pool.map(one,sorted(origins)):self.robots[origin]=robot
    def fetch(self,url):
        url=canonical(url)
        if url in self.cache:return self.cache[url]
        try:
            if not allowed(url):raise ValueError('URL is outside official publisher allowlist')
            p=urllib.parse.urlsplit(url);origin=p.scheme+'://'+p.netloc
            robot=self.robots.get(origin)
            if robot is False or (robot and not robot.can_fetch(AGENT,url)):raise ValueError('Publisher robots policy disallows this path')
            source=self._get(url);doc=Document(source)
            if len(doc.text)<180 or re.search(r'^(?:Access Denied|Just a moment|Robot Challenge|Forbidden)',doc.text,re.I):raise ValueError('Page unavailable or access challenge')
            result=(doc,None)
        except Exception as e:result=(None,type(e).__name__+': '+str(e)[:180])
        self.cache[url]=result;self.reports.append({'url':url,'status':'ok' if result[0] else 'error','error':result[1]});return result

def parse_date(text):
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',text):return dt.date.fromisoformat(text).isoformat()
        clean=re.sub(r'(\d)(st|nd|rd|th)\b',r'\1',text,flags=re.I).replace(',','').replace('.','')
        parts=clean.split();month=next((p for p in parts if p.isalpha()),'').lower()
        number=next((n for m,n in MONTHS.items() if m==month or m.startswith(month[:3])),None)
        nums=[int(p) for p in parts if p.isdigit()];year=next(n for n in nums if n>31);day=next(n for n in nums if n<=31)
        return dt.date(year,number,day).isoformat()
    except (ValueError,TypeError,StopIteration):return None

def extract_dates(text):
    found={'abstract':set(),'full':set()}
    # Only attach a date to an explicit deadline label, never publication/opening dates.
    patterns={
      'abstract':r'(?:abstracts?(?: submission)?(?:s)?\s*(?:deadline|due|by)|(?:deadline|due date)\s*(?:for|of)?\s*(?:submission of )?(?:extended )?abstracts?|(?:submission of )?abstracts?\s*:)',
      'full':r'(?:(?:full[ -]?(?:paper|manuscript)s?|manuscripts?|papers?|submissions?)(?: submission)?\s*(?:deadline|due|by)|(?:deadline|due date)\s*(?:for|of)?\s*(?:full[ -]?)?(?:paper|manuscript|submission)s?|submission deadline\s*:)' }
    for kind,pat in patterns.items():
        for match in re.finditer(pat,text,re.I):
            snippet=text[match.end():match.end()+100]
            stop=re.search(r'\b(?:publication|notification|revis(?:ion|ed)|abstract|submission opens?)\b',snippet,re.I)
            if stop:snippet=snippet[:stop.start()]
            dates=DATE_RE.findall(snippet)
            if dates:
                d=parse_date(dates[0])
                if d:found[kind].add(d)
    # A bare submission deadline beside abstract text is not a manuscript date.
    for m in re.finditer(r'(?:abstract.{0,50}submission deadline|submission deadline.{0,40}abstract)',text,re.I):
        ds=DATE_RE.findall(text[m.start():m.end()+100])
        if ds:
            d=parse_date(ds[0]);found['full'].discard(d)
            if d:found['abstract'].add(d)
    return {k:sorted(v) for k,v in found.items()}

def relevant(text):return [name for name,pat in TOPIC_PATTERNS if re.search(pat,text,re.I)]
def eligible(r,asof):
    try:age=(dt.date.fromisoformat(asof)-dt.date.fromisoformat(r.get('indexing_checked_at',''))).days
    except ValueError:return False
    return r.get('indexing_verified') is True and any(i in ('SSCI','SCIE') for i in r.get('indexing',[])) and bool(r.get('indexing_evidence_url')) and 0<=age<=90
def open_call(r,asof):
    if r.get('review_required') or r.get('status')=='closed':return False
    if r.get('full_paper_deadline') and r['full_paper_deadline']<asof:return False
    if r.get('abstract_required') is True and r.get('abstract_deadline') and r['abstract_deadline']<asof:return False
    return any(r.get(k,'') and r[k]>=asof for k in ('abstract_deadline','full_paper_deadline')) or r.get('status')=='rolling'
def notifiable(r,asof):
    try:fresh=(dt.date.fromisoformat(asof)-dt.date.fromisoformat(r.get('checked_at',''))).days<=7
    except ValueError:return False
    return eligible(r,asof) and open_call(r,asof) and fresh

def update_index(j,doc,asof):
    if not doc:return
    text=doc.text
    # Scope to a single journal evidence page with its exact name or verified ISSN.
    identity=j['name'].casefold() in text.casefold() or any(issn in text for issn in j.get('issns',[]))
    found=[i for i,pat in INDEX_TERMS.items() if re.search(pat,text,re.I)]
    if identity and found:j.update(indexing=found,verified=True,checked_at=asof)
    elif identity and re.search(r'Emerging Sources Citation Index|\bESCI\b',text,re.I):j.update(indexing=['ESCI'],verified=False,checked_at=asof)

def refresh_record(r,j,doc,asof):
    r.update(indexing=j['indexing'],indexing_verified=j['verified'],indexing_checked_at=j['checked_at'])
    if not doc:return
    normalized=lambda s:re.sub(r'\W+',' ',s).strip().casefold()
    title_matches=normalized(r['title']) in normalized(doc.text) or any(SequenceMatcher(None,normalized(r['title']),normalized(h)).ratio()>.88 for h in doc.headings)
    if not title_matches:return
    if re.search(r'closed for submissions|submissions? (?:are |is )?closed|no longer accepting (?:submissions|manuscripts)',doc.text,re.I):r.update(status='closed',checked_at=asof);return
    parsed=extract_dates(doc.text)
    existing_dates=[r[k] for k in ('abstract_deadline','full_paper_deadline') if r.get(k)]
    visible_dates={parse_date(s) for s in DATE_RE.findall(doc.text)}
    # Keep human-reviewed details if their exact dates remain present.
    if existing_dates and all(d in visible_dates for d in existing_dates):r['checked_at']=asof;return
    updates={}
    for kind,key in [('abstract','abstract_deadline'),('full','full_paper_deadline')]:
        values=parsed[kind]
        if len(values)>1:r['review_required']=True;return
        if len(values)==1:updates[key]=values[0]
        elif r.get(key) and r[key] not in visible_dates:r['review_required']=True;return
    if updates:r.update(updates);r.update(checked_at=asof,review_required=False)

def discover_record(url,doc,journals,asof):
    title=(doc.headings[0] if doc.headings else doc.meta.get('og:title','')).strip()
    if not title or len(title)<10 or re.search(r'guest editor|propos(?:e|als?).{0,30}special issue',title,re.I):return None,'not a manuscript call'
    matches=[j for j in journals if j['name'].casefold() in doc.text.casefold() or any(issn in doc.meta.get('citation_issn','') for issn in j.get('issns',[]))]
    if len(matches)!=1:return None,'journal identity not unambiguous or not in verified registry'
    if re.search(r'Multiple participating journals',doc.text,re.I):return None,'multi-journal collection requires specific destination review'
    j=matches[0]
    # Titles and journal scope prevent keywords in editors' bios or article lists from
    # turning an unrelated humanities collection into an AI/education opportunity.
    tags=relevant(title)
    scope_tags=relevant(j['name'])
    tags=list(dict.fromkeys(tags+[t for t in scope_tags if t in ('心理学','教育学','STEM Education','教育技术','Language Education')]))
    if not tags:return None,'research relevance needs review'
    parsed=extract_dates(doc.text)
    if any(len(v)>1 for v in parsed.values()):return None,'multiple conflicting stage deadlines'
    abstract=next(iter(parsed['abstract']),None);full=next(iter(parsed['full']),None)
    if not full:return None,'no unambiguous full manuscript deadline'
    required=None
    if abstract:
        if re.search(r'(?:optional|not required).{0,70}abstract|abstract.{0,70}(?:optional|not required)',doc.text,re.I):required=False
        elif re.search(r'(?:must|required|invited).{0,70}abstract|abstract.{0,70}(?:must|required|invited)',doc.text,re.I):required=True
        else:return None,'abstract requirement needs review'
    r={'id':'auto-'+hashlib.sha256((canonical(url)+j['id']).encode()).hexdigest()[:16],'title':title,'journal':j['name'],'journal_id':j['id'],'publisher':j['publisher'],'cfp_url':url,'abstract_deadline':abstract,'abstract_required':required,'full_paper_deadline':full,'deadline_notes_zh':'自动识别的官方征稿。请在投稿前查看原文中关于格式、资格及截止时区的要求。','topics':tags,'keywords':tags,'summary_zh':'新发现的官方专题征稿。点击查看官方页面了解完整研究范围与投稿要求。','indexing':j['indexing'],'indexing_verified':j['verified'],'indexing_evidence_url':j['evidence_url'],'indexing_checked_at':j['checked_at'],'status':'open','checked_at':asof,'first_seen':asof,'review_required':False}
    return (r,None) if notifiable(r,asof) else (None,'not open or index not verified')

def rss(catalog,base_url,asof):
    ET.register_namespace('atom','http://www.w3.org/2005/Atom')
    root=ET.Element('rss',version='2.0');channel=ET.SubElement(root,'channel')
    for tag,value in [('title','Call Atlas · SSCI / SCIE 征稿'),('link',base_url),('description','AI、教育与心理学专题征稿。仅包含当前通过核验的 SSCI / SCIE 期刊。'),('language','zh-cn'),('lastBuildDate',email.utils.format_datetime(dt.datetime.now(dt.timezone.utc)))]:ET.SubElement(channel,tag).text=value
    ET.SubElement(channel,'{http://www.w3.org/2005/Atom}link',href=base_url+'feed.xml',rel='self',type='application/rss+xml')
    for r in sorted(catalog['records'],key=lambda x:x.get('first_seen',''),reverse=True):
        if not notifiable(r,asof):continue
        item=ET.SubElement(channel,'item');ET.SubElement(item,'title').text=r['title']+' — '+r['journal'];ET.SubElement(item,'link').text=r['cfp_url'];ET.SubElement(item,'guid',isPermaLink='false').text=r['id']
        stamp=dt.datetime.fromisoformat(r.get('first_seen',asof)).replace(tzinfo=dt.timezone.utc);ET.SubElement(item,'pubDate').text=email.utils.format_datetime(stamp)
        desc=f"{r.get('summary_zh','')}\n摘要截止：{r.get('abstract_deadline') or '未单独公布'}\n全文截止：{r.get('full_paper_deadline') or '未公布'}\n收录：{' / '.join(r['indexing'])}\n收录依据：{r['indexing_evidence_url']}\n最近征稿核验：{r.get('checked_at')}"
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
        unique={r['id']:r for _,_,r in pending};lines=[f'@{repo.split("/")[0]} 今日有 **{len(unique)}** 条已核验征稿值得关注。','',f'[打开征稿雷达](https://{repo.split("/")[0]}.github.io/{repo.split("/")[1]}/)','']
        for rid,r in unique.items():
            reasons=sorted({label for _,label,record in pending if record['id']==rid})
            lines.extend([f'### [{r["title"]}]({r["cfp_url"]})',f'{r["journal"]} · {" / ".join(r["indexing"])} · {"；".join(reasons)}',f'- 摘要：{r.get("abstract_deadline") or "未单独公布"}{"（可选）" if r.get("abstract_required") is False else ""}',f'- 全文：{r.get("full_paper_deadline") or "未公布"}',f'- [收录依据]({r["indexing_evidence_url"]})；核验日期 {r["indexing_checked_at"]}', ''])
        lines.extend(f'<!-- call-atlas-event:{key} -->' for key,_,_ in pending)
        api('/issues',{'title':f'[征稿雷达] {asof} · {len(unique)} 条征稿更新','body':'\n'.join(lines)})
        sent.update(key for key,_,_ in pending)
    write('notification-state.json',{'sent':sorted(sent),'pending':[],'last_success':utcnow()})
    return len(pending)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--offline',action='store_true');parser.add_argument('--notify',action='store_true');parser.add_argument('--max-candidates',type=int,default=90);args=parser.parse_args();asof=today()
    catalog=read('data.json',{'records':[]});previous=json.loads(json.dumps(catalog));registry=read('journals.json',{'journals':[]});journals=registry['journals'];sources=read('sources.json',{'sources':[]})['sources'];queue=read('review-queue.json',{'candidates':[]})
    if not args.offline:
        fetcher=Fetcher();urls=[j['evidence_url'] for j in journals]+[r['cfp_url'] for r in catalog['records']]+[s['url'] for s in sources]
        fetcher.prime_robots(urls)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(fetcher.fetch,sorted(set(urls))))
        for j in journals:update_index(j,fetcher.fetch(j['evidence_url'])[0],asof)
        byid={j['id']:j for j in journals}
        for r in catalog['records']:
            if r.get('journal_id') in byid:refresh_record(r,byid[r['journal_id']],fetcher.fetch(r['cfp_url'])[0],asof)
        candidates={};reports=[];known={canonical(r['cfp_url']) for r in catalog['records']}
        for s in sources:
            doc,error=fetcher.fetch(s['url']);links=[]
            if doc:
                for path,label in doc.links:
                    url=canonical(urllib.parse.urljoin(s['url'],path))
                    if allowed(url) and CFP_PATH.search(urllib.parse.urlsplit(url).path) and url not in known:
                        links.append(url);candidates.setdefault(url,{'url':url,'title':label,'publisher':s['publisher']})
            reports.append({'id':s['id'],'status':'ok' if doc else 'error','candidates':len(set(links)),'error':error})
        candidate_list=list(candidates.values())[:args.max_candidates];fetcher.prime_robots([c['url'] for c in candidate_list])
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(fetcher.fetch,[c['url'] for c in candidate_list]))
        reviewed=[]
        for c in candidate_list:
            doc,error=fetcher.fetch(c['url']);r,reason=discover_record(c['url'],doc,journals,asof) if doc else (None,error)
            if r:catalog['records'].append(r)
            else:reviewed.append({**c,'reason':reason,'discovered_at':asof})
        # Keep only latest bounded operational queue, without alerting unverified candidates.
        queue['candidates']=reviewed;queue['unchecked_due_to_limit']=max(0,len(candidates)-len(candidate_list));write('review-queue.json',queue)
        succeeded=sum(r['status']=='ok' for r in fetcher.reports);failed=len(fetcher.reports)-succeeded
        catalog['monitor']={'last_run':utcnow(),'succeeded':succeeded,'failed':failed,'sources':reports,'review_candidates':len(reviewed),'deferred_candidates':queue['unchecked_due_to_limit'],'pages':fetcher.reports}
        catalog['updated_at']=utcnow();write('journals.json',registry)
    base='https://wdeliang978.github.io/special-issue-radar/'
    rss(catalog,base,asof);write('data.json',catalog)
    if args.notify:
        delivered=notify(catalog,previous,asof);print(f'{delivered} notification events delivered or recovered.')
    print(f'{len(catalog["records"])} records; {sum(notifiable(r,asof) for r in catalog["records"])} currently eligible for alerts.')
    if not args.offline:print(f'Official pages read: {catalog["monitor"]["succeeded"]}; unavailable: {catalog["monitor"]["failed"]}.')

if __name__=='__main__':main()
