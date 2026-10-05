import unittest
from collector import Document,parse_date,extract_dates,eligible,open_call,notifiable,allowed,refresh_record,event_key,events,update_index,relevant,discover_record

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

if __name__=='__main__':unittest.main()
