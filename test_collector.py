import unittest
from collector import Document,parse_date,extract_dates,eligible,open_call,notifiable,allowed,refresh_record,event_key,events,update_index,relevant,discover_record,discover_candidates,coverage,pdf_document

class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.today='2026-10-04'
        self.record={'id':'test','title':'AI in Education','indexing':['SSCI'],'indexing_verified':True,'indexing_evidence_url':'https://www.nature.com/journal-info','indexing_checked_at':self.today,'checked_at':self.today,'abstract_required':True,'abstract_deadline':'2026-11-01','full_paper_deadline':'2027-01-15','status':'open'}
        self.journal={'name':'Test Journal','issns':['1234-5678'],'indexing':['SSCI'],'verified':True,'checked_at':self.today}
    def test_deadline_stages(self):
        result=extract_dates('Abstract submission deadline: 30 October 2026. Full manuscript deadline: March 1, 2027. Expected publication: 2028-01-01.')
        self.assertEqual(result,{'abstract':['2026-10-30'],'full':['2027-03-01']})
    def test_ambiguous_dates_retained_as_conflict(self):
        self.assertEqual(extract_dates('Submission deadline: 1 Jan 2027. Submission deadline: 2 Jan 2027.')['full'],['2027-01-01','2027-01-02'])
    def test_invalid_and_missing_year(self):
        self.assertIsNone(parse_date('31 February 2027'))
        self.assertEqual(extract_dates('Submission deadline: 10 June')['full'],[])
        self.assertEqual(extract_dates('Submission opens: 2026-10-30. Publication: 2027-01-01')['full'],[])
    def test_index_gate(self):
        self.assertTrue(eligible(self.record,self.today))
        for changes in [{'indexing':['ESCI']},{'indexing_verified':False},{'indexing_checked_at':'2025-10-04'}]:self.assertFalse(eligible({**self.record,**changes},self.today))
    def test_required_vs_optional_abstract(self):
        self.assertFalse(open_call({**self.record,'abstract_deadline':'2026-10-03'},self.today))
        self.assertTrue(open_call({**self.record,'abstract_deadline':'2026-10-03','abstract_required':False},self.today))
    def test_stale_source_not_notified(self):
        self.assertFalse(notifiable({**self.record,'checked_at':'2026-09-01'},self.today))
        self.assertFalse(notifiable({**self.record,'review_required':True},self.today))
    def test_domain_allowlist(self):
        self.assertTrue(allowed('https://link.springer.com/collections/abc'))
        for url in ['https://springer.com.evil.test/x','http://www.nature.com/x','https://localhost/x','https://user:pass@nature.com/']:
            self.assertFalse(allowed(url))
    def test_access_failure_keeps_last_verification(self):
        record=dict(self.record);refresh_record(record,self.journal,None,'2026-10-06');self.assertEqual(record['checked_at'],self.today)
    def test_navigation_not_journal_proof(self):
        doc=Document('<h1>Test Journal</h1><nav>Science Citation Index Expanded</nav><p>Emerging Sources Citation Index</p>')
        update_index(self.journal,doc,self.today);self.assertEqual(self.journal['verified'],False)
    def test_known_dates_refresh_and_missing_dates_pause(self):
        record=dict(self.record);doc=Document('<h1>AI in Education</h1><p>Abstract submission deadline: 1 November 2026</p><p>Full manuscript deadline: 15 January 2027</p>')
        refresh_record(record,self.journal,doc,'2026-10-05');self.assertEqual(record['checked_at'],'2026-10-05')
        doc2=Document('<h1>AI in Education</h1><p>Details coming soon.</p>');refresh_record(record,self.journal,doc2,'2026-10-06');self.assertTrue(record['review_required'])
    def test_notification_keys_stable_and_include_actual_deadline(self):
        first=events({'records':[self.record]},{'records':[]},self.today);second=events({'records':[self.record]},{'records':[]},self.today)
        self.assertEqual(first,second);self.assertEqual(len(first),2)
    def test_ai_not_substring_of_ordinary_words(self):
        self.assertNotIn('AI in Education',relevant('Our aims include learning'))
    def test_biography_keywords_do_not_admit_unrelated_call(self):
        doc=Document('<h1>Interdisciplinary approaches to antiquity</h1><p>Test Journal</p><p>Editor researches psychology and AI in education</p><p>Submission deadline: 1 January 2027</p>')
        record,reason=discover_record('https://www.nature.com/collections/test',doc,[self.journal],self.today)
        self.assertIsNone(record);self.assertIn('relevance',reason)
    def test_pdf_timetable_ignores_revision_and_final_copy_deadlines(self):
        dates=extract_dates('Manuscript Submission Due Date January 31, 2027 1st round Revision Submission Due Date June 1, 2027 Final Camera-ready Manuscript Due Date November 15, 2027 Estimated Publication Date April 1, 2028')
        self.assertEqual(dates,{'abstract':[],'full':['2027-01-31']})
    def test_journal_linked_external_pdf_is_not_silently_discarded(self):
        source={'url':'https://www.j-ets.net/','publisher':'IFETS','journal_id':'ets','document_hosts':['drive.google.com']}
        url='https://drive.google.com/file/d/abc123/view'
        doc=Document(f'<p>Call for papers for a special issue on <a href="{url}">Generative AI in Education</a></p><p><a href="https://drive.google.com/file/d/scam/view">scam emails</a></p>')
        candidates=discover_candidates(source,doc,set())
        self.assertEqual(len(candidates),1);self.assertEqual(candidates[0]['journal_id'],'ets');self.assertEqual(candidates[0]['format'],'external-pdf')
        self.assertEqual(discover_candidates(source,doc,{url}),[])
        self.assertFalse(allowed(url))
    def test_sciencedirect_h1_journal_name_does_not_replace_call_title(self):
        journal={**self.journal,'id':'lid','name':'Learning and Individual Differences','publisher':'Elsevier','evidence_url':'https://www.sciencedirect.com/insights'}
        title='Evaluating Teachers’ Digital Competence: Instruments and Interventions'
        doc=Document(f'<h1>{journal["name"]}</h1><h3>{title}</h3><p>Submission deadline: 02 April 2027</p>')
        r,reason=discover_record('https://www.sciencedirect.com/special-issue/336575/test',doc,[journal],self.today,{'title':title,'journal_id':'lid'})
        self.assertIsNone(reason);self.assertEqual(r['title'],title)
    def test_pdf_with_references_to_other_journals_uses_verified_source_identity(self):
        j={**self.journal,'id':'ets','name':'Educational Technology & Society','publisher':'IFETS','evidence_url':'https://www.j-ets.net/journal_info/indexing'}
        doc=Document('<p>Educational Technology &amp; Society</p><p>Generative AI in Education</p><p>Manuscript Submission Due Date January 31, 2027</p><p>References: Test Journal</p>');doc.format='pdf'
        r,reason=discover_record('https://www.j-ets.net/call.pdf',doc,[j,self.journal],self.today,{'title':'Generative AI in Education','journal_id':'ets'})
        self.assertIsNone(reason);self.assertEqual(r['journal_id'],'ets')
    def test_unknown_abstract_requirement_pauses_after_abstract_deadline(self):
        self.assertFalse(open_call({**self.record,'abstract_required':None,'abstract_deadline':'2026-10-03'},self.today))
    def test_journal_official_abbreviation_and_monitor_registry(self):
        j={**self.journal,'id':'ets','name':'Educational Technology & Society','identity_aliases':['ET&S'],'publisher':'IFETS','journal_url':'https://www.j-ets.net/'}
        update_index(j,Document('<h1>ET&amp;S - Abstracting and Indexing</h1><p>Social Science Citation Index</p>'),'2026-10-05')
        self.assertEqual(j['checked_at'],'2026-10-05')
        self.assertEqual(coverage([j],[{'id':'ets-source','journal_id':'ets'}])[0]['source_ids'],['ets-source'])
    def test_direct_pdf_extraction(self):
        # A generated one-page PDF exercises the actual reader without a network fixture.
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject,DictionaryObject,NameObject
        import io
        writer=PdfWriter();page=writer.add_blank_page(width=500,height=500)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 20 400 Td (Manuscript deadline: January 31, 2027) Tj ET')
        page[NameObject('/Contents')]=writer._add_object(stream);output=io.BytesIO();writer.write(output)
        doc=pdf_document(output.getvalue());self.assertEqual(extract_dates(doc.text)['full'],['2027-01-31'])
    def test_past_or_undated_prescreen_is_not_mistaken_for_open_submission(self):
        j={**self.journal,'id':'test','publisher':'Test','evidence_url':'https://www.nature.com/info'}
        doc=Document('<h1>AI in Education</h1><p>Test Journal</p><p>Submission deadline: 1 November 2026</p><p>Submit for pre-submission evaluation no later than 1st September. Invited full manuscripts should be submitted later.</p>')
        r,reason=discover_record('https://www.nature.com/collections/test',doc,[j],self.today)
        self.assertIsNone(r);self.assertIn('pre-screening',reason)

if __name__=='__main__':unittest.main()
