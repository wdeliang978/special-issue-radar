import unittest
from import_journals import merge_rows,homepage
from collector import eligible,Document,update_index,index_fields,journal_identity,discover_hubs,candidate_batch,notifiable,discover_record,canonical,destination_journals,extract_dates,record_identity

class RegistryTests(unittest.TestCase):
    def row(self,name='Science Education',identifiers=None,edition='SSCI',row=2,sheet='education-ssci'):
        return {'name':name,'issns':identifiers or ['0036-8326'],'publisher':'WILEY','edition':edition,'category':'EDUCATION','row':row,'sheet':sheet}
    def test_issn_dedup_retains_distinct_science_titles_and_both_editions(self):
        rows=[self.row(),self.row('SCIENCE EDUCATION',edition='SCIE',sheet='education-sci'),self.row('Science & Education',['0926-7220'],row=3)]
        journals,counts=merge_rows([],rows,'list.xlsx','2026-10-05')
        self.assertEqual(counts['unique_imported'],2);self.assertEqual(journals[0]['indexing'],['SCIE','SSCI']);self.assertEqual(len(journals[0]['registry_provenance']['rows']),2)
    def test_import_does_not_overwrite_official_downgrade_or_remove_existing_ai(self):
        current=[{'id':'a','name':'Science Education','issns':['0036-8326'],'indexing':['ESCI'],'verified':False,'checked_at':'2026-10-01','evidence_url':'https://example.test/indexing'}, {'id':'ai','name':'AI Journal','issns':['1111-1111']}]
        journals,counts=merge_rows(current,[self.row()],'list.xlsx','2026-10-05')
        self.assertEqual(counts['added'],0);self.assertEqual(len(journals),2);self.assertEqual(journals[0]['indexing'],['ESCI']);self.assertFalse(journals[0]['verified'])
    def test_identical_names_with_different_issns_stay_separate(self):
        journals,_=merge_rows([],[self.row(),self.row(identifiers=['1111-1111'])],'list.xlsx','2026-10-05')
        self.assertEqual(len(journals),2)
    def test_jcr_gate_requires_provenance_matching_edition_and_snapshot_age(self):
        journals,_=merge_rows([],[self.row()],'list.xlsx','2026-10-05');r=index_fields(journals[0])
        self.assertTrue(eligible(r,'2026-10-05'))
        self.assertFalse(eligible(r,'2027-06-03'))
        self.assertFalse(eligible({**r,'indexing':['SCIE']},'2026-10-05'))
        self.assertFalse(eligible({**r,'indexing_provenance':None},'2026-10-05'))
        self.assertFalse(eligible({**r,'indexing':['ESCI']},'2026-10-05'))
    def test_homepage_biography_cannot_promote_index_but_index_section_can_downgrade(self):
        j=merge_rows([],[self.row()],'list.xlsx','2026-10-05')[0][0]
        update_index(j,Document('<h1>Science Education</h1><p>Our editor also edits SCIE journals</p>'),'2026-10-06','https://example.test')
        self.assertEqual(j['evidence_type'],'user_jcr')
        update_index(j,Document('<h1>Science Education</h1><h2>Abstracting and indexing</h2><p>Emerging Sources Citation Index</p>'),'2026-10-06','https://example.test')
        self.assertEqual(j['indexing'],['ESCI']);self.assertFalse(j['verified']);self.assertFalse(eligible(index_fields(j),'2026-10-06'))
    def test_short_journal_title_does_not_match_word_fragment(self):
        self.assertFalse(journal_identity({'name':'System'},'Intelligent systems in Education'))
        self.assertTrue(journal_identity({'name':'Science & Education'},'Science and Education'))
    def test_navigation_hub_discovered_without_becoming_index_evidence(self):
        doc=Document('<h1>Science Education</h1><nav><a href="/journal/100/collections">Collections</a></nav>')
        source={'id':'a','journal_id':'a','url':'https://link.springer.com/journal/100','publisher':'Springer Nature'}
        hubs=discover_hubs(source,doc);self.assertEqual(len(hubs),1);self.assertEqual(hubs[0]['journal_id'],'a');self.assertNotIn('Collections',doc.text)
    def test_candidate_budget_rotates_across_journals_and_checks(self):
        c={str(n):{'url':str(n),'journal_id':'a' if n<3 else 'b','publisher':'P'} for n in range(5)}
        first=candidate_batch(c,[],2);self.assertEqual({x['journal_id'] for x in first},{'a','b'})
        history=[{**x,'last_checked':'2026-10-05'} for x in first]
        second=candidate_batch(c,history,2);self.assertFalse({x['url'] for x in first}&{x['url'] for x in second})
    def test_weekly_freshness_includes_eighth_day_and_then_pauses(self):
        j=merge_rows([],[self.row()],'list.xlsx','2026-10-05')[0][0]
        r={**index_fields(j),'checked_at':'2026-10-05','full_paper_deadline':'2027-01-01','status':'open'}
        self.assertTrue(notifiable(r,'2026-10-13'));self.assertFalse(notifiable(r,'2026-10-14'))
    def test_legacy_homepage_normalization(self):
        self.assertEqual(homepage('http://www.tandfonline.com/toc/RSSE20/current'),'https://www.tandfonline.com/journals/rsse20')
        self.assertEqual(homepage('http://www.springer.com/10734'),'https://link.springer.com/journal/10734')
        self.assertEqual(homepage('http://epx.sagepub.com'),'https://journals.sagepub.com/home/epx')
    def test_closed_collection_cannot_be_discovered_as_open(self):
        j=merge_rows([],[self.row()],'list.xlsx','2026-10-05')[0][0]
        doc=Document('<h1>AI in Education</h1><p>Science Education</p><p>Closed for submissions</p><p>Submission deadline: 1 January 2027</p>')
        r,reason=discover_record('https://link.springer.com/collections/closed',doc,[j],'2026-10-05')
        self.assertIsNone(r);self.assertIn('closed',reason)
    def test_cookie_redirects_and_duplicate_publisher_titles_share_identity(self):
        self.assertEqual(canonical('https://link.springer.com/collections/abc?error=cookies_not_supported&code=random'),'https://link.springer.com/collections/abc')
        self.assertIn('token=public-file',canonical('https://www.hogrefe.com/index.php?eID=dumpFile&token=public-file'))
        self.assertEqual(record_identity({'journal_id':'x','title':'Call for Papers - Equity in STEM'}),record_identity({'journal_id':'x','title':'Equity in STEM'}))
    def test_participating_journal_beats_generic_prose_and_discovery_context(self):
        higher={'id':'h','name':'Higher Education','journal_url':'https://link.springer.com/journal/10734'}
        hssc={'id':'s','name':'Humanities and Social Sciences Communications','journal_url':'https://www.nature.com/palcomms'}
        doc=Document('<h1>Inclusive Education</h1><p>Research on higher education</p><a href="/palcomms">Journal home</a>')
        self.assertEqual(destination_journals('https://www.nature.com/collections/abc',doc,[higher,hssc],{'journal_id':'h'}),[hssc])
    def test_date_first_timetable_reveals_earlier_abstract_and_full_deadline(self):
        text='Submission deadline 31 July 2027\n31 May 2026: Extended Abstracts submitted (1500 words)\n15 June 2026: Full manuscript invitations sent\n30 September 2026: Full manuscripts submitted'
        self.assertEqual(extract_dates(text),{'abstract':['2026-05-31'],'full':['2026-09-30','2027-07-31']})
    def test_undated_abstract_invitation_cannot_use_only_the_full_deadline(self):
        j=merge_rows([],[self.row()],'list.xlsx','2026-10-05')[0][0]
        doc=Document('<h1>AI in Education</h1><p>Science Education</p><p>Authors whose abstracts are accepted will be invited to submit full manuscripts.</p><p>Submission deadline: 1 January 2027</p>')
        r,reason=discover_record('https://link.springer.com/collections/abc',doc,[j],'2026-10-05')
        self.assertIsNone(r);self.assertIn('abstract prerequisite',reason)
    def test_abstract_deadline_after_submission_instructions(self):
        dates=extract_dates('Please submit a single abstract (approx. 1000 words) alongside a short biographical note about the authors (approx. 50 words per author) by November 30th, 2026.')
        self.assertEqual(dates['abstract'],['2026-11-30'])

if __name__=='__main__':unittest.main()
