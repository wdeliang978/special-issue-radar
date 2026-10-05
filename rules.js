export const TOPICS = ['全部方向','AI in Education','AI / NLP','Explainable AI','教育技术','教育学','心理学','STEM Education','Language Education'];
export const dayNumber = s => s && /^\d{4}-\d{2}-\d{2}$/.test(s) ? Date.parse(s+'T00:00:00Z')/86400000 : null;
export const todayISO = () => new Intl.DateTimeFormat('sv-SE',{timeZone:'America/New_York'}).format(new Date());
export function isEligible(r, today=todayISO()) {
  return r.indexing_verified===true && Array.isArray(r.indexing) && r.indexing.some(i=>['SSCI','SCIE'].includes(i)) && !!r.indexing_evidence_url && dayNumber(r.indexing_checked_at)!==null && dayNumber(today)-dayNumber(r.indexing_checked_at)<=90;
}
export function statusFor(r,today=todayISO()) {
  if (r.review_required) return 'review';
  if (r.status==='closed' || (r.full_paper_deadline && r.full_paper_deadline<today)) return 'closed';
  if (r.abstract_required!==false && r.abstract_deadline && r.abstract_deadline<today) return 'invitation';
  if (r.submission_opens && r.submission_opens>today) return 'upcoming';
  if ((r.full_paper_deadline && r.full_paper_deadline>=today) || (r.abstract_deadline && r.abstract_deadline>=today) || r.status==='rolling') return 'open';
  return 'unknown';
}
export function nextDeadline(r,today=todayISO()) {
  return [r.abstract_deadline,r.full_paper_deadline].filter(d=>d && d>=today).sort()[0]||null;
}
export function matches(r,filters,today=todayISO()) {
  if (!isEligible(r,today)) return false;
  const status=statusFor(r,today);
  if (filters.status==='open' && !['open','upcoming'].includes(status)) return false;
  if (filters.status==='closed' && !['closed','invitation'].includes(status)) return false;
  if (filters.publisher!=='all' && r.publisher!==filters.publisher) return false;
  if (filters.index!=='all' && !r.indexing.includes(filters.index)) return false;
  if (filters.topic!=='全部方向' && !r.topics.includes(filters.topic)) return false;
  const words=(filters.query||'').normalize('NFKC').toLowerCase().trim().split(/\s+/).filter(Boolean);
  const text=[r.title,r.journal,r.publisher,r.summary_zh,...r.topics,...(r.keywords||[])].join(' ').normalize('NFKC').toLowerCase();
  return words.every(w=>text.includes(w));
}
const icsEscape = v => String(v||'').replace(/\\/g,'\\\\').replace(/\r?\n/g,'\\n').replace(/,/g,'\\,').replace(/;/g,'\\;');
function fold(line) {
  let out='', current='',size=0;
  for(const char of line){const n=new TextEncoder().encode(char).length;if(size+n>73){out+=current+'\r\n ';current='';size=1;}current+=char;size+=n;}return out+current;
}
export function toICS(records,today=todayISO()) {
  const lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Call Atlas//CFP Radar//ZH','CALSCALE:GREGORIAN','X-WR-CALNAME:Call Atlas 征稿截止日期'];
  for(const r of records) for(const [key,label] of [['abstract_deadline','摘要'],['full_paper_deadline','全文']]) {
    const d=r[key];if(!d || d<today) continue;
    const end=new Date((dayNumber(d)+1)*86400000).toISOString().slice(0,10).replaceAll('-','');
    lines.push('BEGIN:VEVENT',`UID:${icsEscape(r.id)}-${key}@call-atlas`,`DTSTAMP:${today.replaceAll('-','')}T000000Z`,`DTSTART;VALUE=DATE:${d.replaceAll('-','')}`,`DTEND;VALUE=DATE:${end}`,`SUMMARY:${icsEscape(`[${label}截止] ${r.title}`)}`,`DESCRIPTION:${icsEscape(`${r.journal}\n${r.cfp_url}\n${r.deadline_notes_zh||r.deadline_notes||''}\n截止时区未说明时，请以出版社要求为准。`)}`,`URL:${r.cfp_url}`,'END:VEVENT');
  }
  lines.push('END:VCALENDAR');return lines.map(fold).join('\r\n')+'\r\n';
}
