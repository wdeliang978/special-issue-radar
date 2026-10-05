import gzip
import unittest
import urllib.error
from email.message import Message
from unittest.mock import patch

from collector import AccessError, Document, Fetcher, decode_response, discover_candidates, destination_journals, error_code, journal_identity, record_identity, extract_dates, refresh_record, submission_document, submission_windows
from publisher_directories import collect_taylor_francis,match_tf_journal


class AccessTests(unittest.TestCase):
    def test_date_first_rows_do_not_borrow_notification_dates(self):
        text='November 15, 2026: Deadline for abstract submissions: https://example.org/form\nDecember 20, 2026: Notification of abstract review\nApril 1, 2027: Deadline for full paper submissions\nJune 1, 2027: Notification of first-round peer review results'
        self.assertEqual(extract_dates(text),{'abstract':['2026-11-15'],'full':['2027-04-01']})

    def test_abstract_submission_due_is_not_a_full_paper_deadline(self):
        text='Abstract Submission Due Date: 31 October 2026.\nManuscript Submission Due Date: 31 May 2027.\nDeadline for submission of revised papers: 28 February 2028'
        self.assertEqual(extract_dates(text),{'abstract':['2026-10-31'],'full':['2027-05-31']})

    def test_pdf_feedback_line_wrap_does_not_capture_next_revision_date(self):
        text='February 15, 2027: Full paper submissions due\nApril 15, 2027: Feedback to authors of full paper\nsubmissions due\nMay 15, 2027: Revised manuscripts due'
        self.assertEqual(extract_dates(text),{'abstract':[],'full':['2027-02-15']})

    def test_prose_and_parenthetical_abstract_deadlines(self):
        self.assertEqual(extract_dates('The deadline for the submission of abstracts is 1 February 2027. Feedback will be provided by 15 March 2027.')['abstract'],['2027-02-01'])
        self.assertEqual(extract_dates('Final abstracts (250 words) due: Oct 25, 2026')['abstract'],['2026-10-25'])
        self.assertEqual(extract_dates('Abstracts of no more than 750 words should be submitted by Monday 2 November 2026.')['abstract'],['2026-11-02'])

    def test_timetable_submission_window_uses_closing_date(self):
        text='30 March 2026 – Abstract submission deadline\n30 April 2026 – Guest editors decisions\n15 August 2026-15 October 2026 – Full article submission deadline'
        self.assertEqual(extract_dates(text),{'abstract':['2026-03-30'],'full':['2026-10-15']})

    def test_abstract_instructions_do_not_borrow_later_decision_date(self):
        text='Abstracts should be submitted by Monday 2 November 2026.\nPlease submit your abstract via this form.\nDecisions on abstracts will be communicated by 30 November 2026.\nAnnouncement of accepted abstracts: 1 December 2026'
        self.assertEqual(extract_dates(text),{'abstract':['2026-11-02'],'full':[]})

    def test_api_can_confirm_an_unchanged_previously_verified_abstract_date(self):
        j={'indexing':['SSCI'],'verified':True,'checked_at':'2026-10-05','evidence_url':'https://example.org/index'}
        record={'title':'AI in Education','cfp_url':'https://example.org/call','abstract_deadline':'2026-10-31','full_paper_deadline':'2027-03-31','review_required':False}
        doc=Document('<h1>AI in Education</h1><p>Abstract deadline: October 2026</p><p>Manuscript deadline: 31 March 2027</p>')
        doc.additional_deadlines=['31 October 2026']
        refresh_record(record,j,doc,'2026-10-05')
        self.assertFalse(record['review_required']);self.assertEqual(record['checked_at'],'2026-10-05')
        doc.additional_deadlines=['15 November 2026']
        refresh_record(record,j,doc,'2026-10-05')
        self.assertTrue(record['review_required'])

    def test_gzipped_official_page_remains_readable_and_identifiable(self):
        headers=Message();headers['Content-Type']='text/html; charset=utf-8';headers['Content-Encoding']='gzip'
        body='<h1>Education as Change</h1><a href="announcements/call-for-papers/ai">AI special issue</a>'
        doc=Document(decode_response(gzip.compress(body.encode()),headers))
        self.assertTrue(journal_identity({'name':'Education as Change'},doc.text))
        self.assertEqual(len(doc.links),1)

    def test_oversized_compressed_response_is_bounded(self):
        headers=Message();headers['Content-Type']='text/html';headers['Content-Encoding']='gzip'
        with self.assertRaisesRegex(AccessError,'4 MB'):decode_response(gzip.compress(b'a'*4_000_001),headers)

    def test_robots_http_failure_is_distinct_from_explicit_disallow(self):
        f=Fetcher();url='https://www.nature.com/collections/abc'
        denied=urllib.error.HTTPError('https://www.nature.com/robots.txt',403,'Forbidden',{},None)
        with patch.object(f,'_get',side_effect=denied):f.prime_robots([url])
        self.assertIsNone(f.fetch(url)[0]);self.assertEqual(f.reports[-1]['error_code'],'robots_unavailable')
        f=Fetcher()
        with patch.object(f,'_get',return_value='User-agent: *\nDisallow: /collections/'):
            f.prime_robots([url]);self.assertIsNone(f.fetch(url)[0])
        self.assertEqual(f.reports[-1]['error_code'],'robots_disallowed')

    def test_redirected_relative_links_use_final_official_location(self):
        doc=Document('<a href="call-for-papers/ai">AI special issue</a>');doc.url='https://www.nature.com/new/'
        source={'url':'https://www.nature.com/old/','journal_id':'x','publisher':'Nature'}
        self.assertEqual(discover_candidates(source,doc,set())[0]['url'],'https://www.nature.com/new/call-for-papers/ai')

    def test_human_challenge_and_empty_dynamic_shell_are_separate(self):
        for content,expected in [('<h1>Just a moment</h1><p>Verify you are human</p>','challenge'),('<div id="app"></div>','dynamic_content')]:
            f=Fetcher()
            with patch.object(f,'_get',return_value=content):self.assertIsNone(f.fetch('https://www.nature.com/')[0])
            self.assertEqual(f.reports[-1]['error_code'],expected)

    def test_accents_and_punctuation_do_not_hide_same_journal(self):
        self.assertTrue(journal_identity({'name':'Ensenanza de Las Ciencias'},'Enseñanza de las Ciencias'))
        self.assertFalse(journal_identity({'name':'System'},'Modern educational systems'))

    def test_publisher_robots_without_content_type_and_longest_rule(self):
        body=b'User-agent: *\nDisallow: /\nAllow: /journal*\nDisallow: /journal/*/private$\n'
        text=decode_response(body,Message(),is_robots=True)
        f=Fetcher()
        with patch.object(f,'_get',return_value=text):f.prime_robots(['https://link.springer.com/journal/42'])
        f.check_permission('https://link.springer.com/journal/42')
        with self.assertRaises(AccessError):f.check_permission('https://link.springer.com/journal/42/private')
        with self.assertRaises(AccessError):decode_response(b'<html>Verification required</html>',Message(),is_robots=True)

    def test_shared_publisher_links_cannot_change_aom_destination(self):
        j={'id':'amle','name':'Academy of Management Learning & Education','publisher_journal_code':'amle','journal_url':'https://www.aom.org/publications/journals/learning-and-education/'}
        doc=Document('<h1>AMP Call for Special Issue Papers</h1><a href="'+j['journal_url']+'">Other journals</a>')
        self.assertEqual(destination_journals('https://www.aom.org/event/amp-call-for-special-issue-papers-x',doc,[j],{}),[])
        self.assertEqual(record_identity({'journal_id':'x','title':'Collection: Embodied Learning'}),record_identity({'journal_id':'x','title':'Embodied Learning'}))

    def test_aom_related_events_cannot_supply_another_calls_deadline(self):
        doc=Document('<h1>AMLE call</h1><p>We invite special issue submissions to occur between 1 November 2026 and 14 December 2026.</p><p>Add to calendar</p><p>AMP event. Submission deadline: 31 January 2027</p>')
        scoped=submission_document('https://www.aom.org/event/amle-call-for-papers-test',doc)
        self.assertEqual(extract_dates(scoped.text)['full'],['2026-12-14'])
        self.assertEqual(submission_windows(scoped.text),[('2026-11-01','2026-12-14')])
        self.assertIn('AMP event',doc.text)

    def test_official_directory_requires_complete_pages_and_exact_journal_mapping(self):
        j={'id':'distance','name':'Distance Education','publisher':'Taylor & Francis','journal_url':'https://www.tandfonline.com/journals/cdie20'}
        row={'id':17,'link':'https://callforpapers.taylorandfrancis.com/special_issues/ai/','special_issues':{
            '_special_issues_journal_select':['CDIE'],'_special_issues_journal_title':['Distance Education'],
            '_special_issues_title':['Artificial intelligence and distance learning'],
            '_special_issues_copy':['<p>Research on education and learning with artificial intelligence in distance education. This call requires an abstract before the full paper can be considered.</p>'],
            '_special_issues_submissions_instructions':['<p>Abstract deadline: 1 November 2026</p>'],
            '_special_issues_deadline':['1 February 2027']}}
        class FakeFetcher:
            def prime_robots(self,urls):pass
            def fetch_json(self,url,headers):return ([row],{'X-WP-Total':'1','X-WP-TotalPages':'1'},None) if '/special_issues?' in url else ([],{'X-WP-Total':'0','X-WP-TotalPages':'0'},None)
        report,candidates,docs=collect_taylor_francis(FakeFetcher(),[j],set())
        self.assertTrue(report['complete']);self.assertEqual(len(candidates),1)
        doc=docs[candidates[0]['url']]
        self.assertIn('Abstract deadline',doc.text);self.assertIn('Manuscript deadline',doc.text)
        self.assertEqual(doc.format,'publisher-api')
        self.assertEqual(report['scope_journal_ids'],['distance'])
        class BrokenFetcher(FakeFetcher):
            def fetch_json(self,url,headers):return None,{},'HTTP 403'
        report,_,_=collect_taylor_francis(BrokenFetcher(),[j],set())
        self.assertFalse(report['complete']);self.assertEqual(report['status'],'error')
        wrong={**j,'id':'other','name':'Different Journal','journal_url':'https://www.tandfonline.com/journals/xxxx20'}
        conflict={**row,'special_issues':{**row['special_issues'],'_special_issues_journal_select':['XXXX']}}
        self.assertIsNone(match_tf_journal(conflict,'special_issues',[j,wrong]))


if __name__=='__main__':unittest.main()
