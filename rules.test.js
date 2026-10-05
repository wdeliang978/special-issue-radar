import test from 'node:test';
import assert from 'node:assert/strict';
import {isEligible,statusFor,matches,toICS,registryAccess} from './rules.js';
const now='2026-10-04';
const base={id:'sample',title:'AI in learning',journal:'Example Journal',publisher:'Example',summary_zh:'人工智能学习',topics:['AI in Education'],indexing:['SSCI'],indexing_verified:true,indexing_evidence_url:'https://example.com/indexing',indexing_checked_at:now,checked_at:now,abstract_deadline:'2026-10-01',full_paper_deadline:'2027-03-01',cfp_url:'https://example.com/cfp',abstract_required:true};

test('a complete publisher directory is separate from a readable journal homepage',()=>{
  const j={id:'x',source_ids:['home']},sources=[{id:'home',journal_id:'x',status:'error',error_code:'access_denied'}];
  const directories=[{scope_journal_ids:['x'],status:'ok',complete:true}];
  assert.equal(registryAccess(j,{sources,directories}).status,'directory');
  assert.equal(registryAccess(j,{sources,directories:[{...directories[0],complete:false}]}).status,'error');
  assert.equal(registryAccess(j,{sources,directories:[{...directories[0],scope_journal_ids:['other']}]}).status,'error');
  assert.equal(registryAccess(j,{sources:[{...sources[0],status:'ok'}],directories}).status,'ok');
  assert.equal(registryAccess(j,{sources:[{...sources[0],status:'ok',purpose:'identity_only'}]}).status,'error');
  assert.ok(registryAccess(j,{sources:[{...sources[0],status:'ok',purpose:'identity_only'}]}).errors.includes('cfp_unchecked'));
});
test('ESCI, missing proof, and stale indexing never pass',()=>{assert.equal(isEligible({...base,indexing:['ESCI']},now),false);assert.equal(isEligible({...base,indexing_verified:false},now),false);assert.equal(isEligible({...base,indexing_checked_at:'2026-01-01'},now),false);assert.equal(isEligible(base,now),true);});
test('imported JCR evidence is explicit, edition-specific and time-bounded',()=>{
  const r={...base,indexing_evidence_url:null,indexing_evidence_type:'user_jcr',indexing_provenance:{kind:'user_jcr',file:'list.xlsx',period:'2026-06',rows:[{sheet:'education-ssci',row:2,edition:'SSCI'}]}};
  assert.equal(isEligible(r,now),true);assert.equal(isEligible(r,'2027-06-03'),false);
  assert.equal(isEligible({...r,indexing:['SCIE']},now),false);assert.equal(isEligible({...r,indexing_provenance:null},now),false);
  assert.equal(isEligible({...r,indexing:['ESCI'],indexing_verified:false},now),false);
  assert.equal(isEligible({...base,indexing_checked_at:'2027-01-01'},now),false);
});
test('mandatory abstract cutoff differs from optional abstract cutoff',()=>{assert.equal(statusFor(base,now),'invitation');assert.equal(statusFor({...base,abstract_required:false},now),'open');assert.equal(statusFor({...base,abstract_deadline:now},now),'open');});
test('an unspecified abstract requirement is not assumed optional after its cutoff',()=>{assert.equal(statusFor({...base,abstract_required:null},now),'invitation');});
test('review, expired, unknown dates do not masquerade as open calls',()=>{assert.equal(statusFor({...base,review_required:true},now),'review');assert.equal(statusFor({...base,full_paper_deadline:'2026-09-30'},now),'closed');assert.equal(statusFor({...base,abstract_deadline:null,full_paper_deadline:null},now),'unknown');});
test('intersection filters do not lose strict indexing or eligibility',()=>{const f={status:'open',publisher:'all',index:'SSCI',topic:'AI in Education',query:'AI learning'};assert.equal(matches(base,f,now),false);assert.equal(matches({...base,abstract_required:false},f,now),true);assert.equal(matches({...base,abstract_required:false,indexing:['ESCI']},f,now),false);});
test('calendar emits actual separate future dates, escapes text, and folds UTF-8',()=>{const s=toICS([{...base,title:'测试研究'.repeat(35)+', NLP; AI',abstract_deadline:'2026-10-30'}],now);assert.equal((s.match(/BEGIN:VEVENT/g)||[]).length,2);assert.match(s,/DTSTART;VALUE=DATE:20261030/);assert.match(s,/DTEND;VALUE=DATE:20261031/);assert.match(s,/\\,/);assert.ok(s.split('\r\n').every(l=>Buffer.byteLength(l)<=75));});
