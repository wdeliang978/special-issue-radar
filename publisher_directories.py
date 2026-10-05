"""Adapters for public directories linked by official publisher websites.

Directory availability is separate from journal homepage availability. A complete
directory is not evidence that no other editor-hosted calls exist.
"""
import html
import re
from urllib.parse import urlencode,urlsplit

TF_INDEX='https://authorservices.taylorandfrancis.com/call-for-papers/'
TF_API='https://callforpapers.taylorandfrancis.com/wp-json/wp/v2/'
TF_TYPES=('special_issues','article_collections')


def values(row,kind,field):
    value=row.get(kind,{}).get('_'+kind+'_'+field,[])
    return value if isinstance(value,list) else [value] if isinstance(value,str) else []


def journal_code(j):
    path=urlsplit(j.get('journal_url') or '').path
    match=re.search(r'/(?:journals|toc|loi)/([a-z]{4})\d*',path,re.I)
    return match[1].lower() if match else None


def match_tf_journal(row,kind,journals):
    normalize=lambda s:re.sub(r'\W+',' ',html.unescape(s).casefold().replace('&',' and ')).strip()
    names={normalize(v) for v in values(row,kind,'journal_title') if isinstance(v,str) and v.strip()}
    codes={v.casefold() for v in values(row,kind,'journal_select') if isinstance(v,str) and v.strip()}
    byname=[j for j in journals if any(normalize(n) in names for n in [j['name']]+j.get('aliases',[]))]
    bycode=[j for j in journals if journal_code(j) in codes]
    # A contradictory name/code mapping requires review, never a guessed target.
    if byname and bycode and {j['id'] for j in byname}!={j['id'] for j in bycode}:return None
    found=bycode or byname
    return found[0] if len(found)==1 else None


def collect_taylor_francis(fetcher,journals,known):
    from collector import Document,canonical,utcnow
    scope=[j for j in journals if j['publisher']=='Taylor & Francis' or (urlsplit(j.get('journal_url') or '').hostname or '').endswith('.tandfonline.com')]
    report={'id':'taylor-francis-public-directory','publisher':'Taylor & Francis','url':TF_INDEX,'checked_at':utcnow(),'status':'error','complete':False,'scope_journal_ids':[j['id'] for j in scope],'items':0,'pages':0,'candidates':0,'journal_counts':{},'error':None,'error_code':None,'endpoints':[]}
    candidates=[];documents={};seen=set();errors=[]
    fetcher.prime_robots([TF_API])
    for kind in TF_TYPES:
        fields=['id','link']+[f'{kind}._{kind}_{key}' for key in ('journal_select','journal_title','title','copy','submissions_instructions','deadline','deadline2')]
        expected=None;total_pages=None;items=[]
        for page in range(1,51):
            url=TF_API+kind+'?'+urlencode({'per_page':100,'page':page,'_fields':','.join(fields)})
            rows,headers,error=fetcher.fetch_json(url,{'X-Request-Source':'JTF/AS/CFP'})
            report['pages']+=1
            if error or not isinstance(rows,list):errors.append(error or 'Unexpected directory schema');break
            try:
                count=int(headers['X-WP-Total']);pages=int(headers['X-WP-TotalPages'])
                if count<0 or pages<0 or pages>50:raise ValueError('Invalid directory pagination')
                if expected is not None and (count!=expected or pages!=total_pages):raise ValueError('Directory changed during pagination')
                expected=count;total_pages=pages
            except (KeyError,TypeError,ValueError) as e:errors.append(str(e));break
            if any(not isinstance(r,dict) or not isinstance(r.get('link'),str) or not isinstance(r.get(kind),dict) for r in rows):errors.append('Unexpected directory item schema');break
            items.extend(rows)
            print(f'  {kind}: page {page}/{total_pages}, {len(items)}/{expected} entries.',flush=True)
            if page>=total_pages:break
        if expected is None or len(items)!=expected or len({r['link'] for r in items})!=len(items):errors.append(kind+': incomplete or duplicate directory pages')
        report['endpoints'].append({'type':kind,'expected':expected,'read':len(items),'pages':total_pages})
        report['items']+=len(items)
        for row in items:
            j=match_tf_journal(row,kind,scope)
            if not j:continue
            url=canonical(row['link']);host=urlsplit(url).hostname
            if host not in ('callforpapers.taylorandfrancis.com','think.taylorandfrancis.com') or urlsplit(url).scheme!='https':continue
            if url in seen:continue
            seen.add(url)
            title=html.unescape(' '.join(str(v) for v in values(row,kind,'title'))).strip()
            copy='\n'.join(str(v) for v in values(row,kind,'copy'))
            instructions='\n'.join(str(v) for v in values(row,kind,'submissions_instructions'))
            deadlines=values(row,kind,'deadline')
            journal_titles=' / '.join(str(v) for v in values(row,kind,'journal_title'))
            # These are official API fields rendered by the publisher's own CFP
            # widget. Keep all stage dates in the copy; conflicting dates fail
            # the ordinary submission-stage checks in collector.py.
            body='<h1>'+html.escape(title)+'</h1><p>'+html.escape(journal_titles)+'</p>'+copy+'<section>'+instructions+'</section>'
            if j.get('journal_url'):body+='<a href="'+html.escape(j['journal_url'],quote=True)+'">Destination journal</a>'
            for deadline in deadlines:body+='<p>Manuscript deadline: '+html.escape(str(deadline))+'</p>'
            doc=Document(body);doc.url=url;doc.format='publisher-api'
            doc.additional_deadlines=[v for v in values(row,kind,'deadline2') if isinstance(v,str) and v.strip()]
            if len(doc.text)<180 or not copy.strip():continue
            doc.verification_url=TF_API+kind+'/'+str(row['id'])+'?'+urlencode({'_fields':','.join(fields)}) if row.get('id') else TF_INDEX
            documents[url]=doc
            # The official frontend also links the same post at its legacy host.
            # Cache both verified API-derived representations for old records.
            legacy=url.replace('https://callforpapers.taylorandfrancis.com/','https://think.taylorandfrancis.com/')
            documents[legacy]=doc
            report['journal_counts'][j['id']]=report['journal_counts'].get(j['id'],0)+1
            if url not in known and legacy not in known:
                candidates.append({'url':url,'title':title,'journal_id':j['id'],'publisher':j['publisher'],'discovery_source_url':TF_INDEX,'format':'publisher-api','verification_url':doc.verification_url})
    report['complete']=not errors
    report['status']='ok' if not errors else 'error'
    report['error']='; '.join(dict.fromkeys(errors))[:700] if errors else None
    report['error_code']='directory_incomplete' if errors else None
    report['candidates']=len(candidates)
    return report,candidates,documents
