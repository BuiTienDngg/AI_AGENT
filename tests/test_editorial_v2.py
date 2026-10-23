import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from game_seo.core import ROOT,load_json,save_json
from game_seo.editorial import policy,ledger,review_gate,chief,retain_brief,assert_preserved,REVIEW_METRICS
from game_seo.qa import validate
from game_seo.translation import validate_translation
from game_seo.stage_context import prepare_stage_context
from test_pipeline import fixtures,translated_fixture


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.work=Path(self.temp.name)
        self.article,self.sources,self.images,self.frames=fixtures(self.work)
        self.cfg=policy(self.work,load_json(ROOT/'config.json'))
    def tearDown(self):
        self.temp.cleanup()

    def review(self,role,article=None):
        article=article or self.article
        return {'pass_editorial':True,'issues':[],'strengths':[],
                'scores':[{'metric':metric,'score':10,'reason':'Specific visible choice.',
                           'revision':'','evidence':[{'path':'sections[0].paragraphs[0]',
                           'quote':article['sections'][0]['paragraphs'][0]['text'][:45]}]}
                          for metric in REVIEW_METRICS[role]]}

    def test_policy_omits_unknown_or_absent_story_without_forcing_research(self):
        self.assertNotIn('Story',self.cfg['required_sections'])
        self.assertEqual(self.cfg['min_text_sources'],0)
        self.assertEqual(self.cfg['commons_images'],0)
        save_json(self.work/'game_brief.json',{'story_status':'PUBLISHER_CONFIRMED_ABSENT','story':'No invented history'})
        self.assertNotIn('Story',policy(self.work,self.cfg)['required_sections'])
        save_json(self.work/'game_brief.json',{'story':'Publisher-supplied premise'})
        self.assertIn('Story',policy(self.work,self.cfg)['required_sections'])

    def test_v2_accepts_gameplay_only_but_rejects_invalid_citations(self):
        article=copy.deepcopy(self.article)
        article['sections']=[s for s in article['sections'] if s['heading'] in self.cfg['required_sections']]
        for section in article['sections']:
            for paragraph in section['paragraphs']:
                import re
                paragraph['text']=re.sub(r'\[\[SRC\d+\]\]','',paragraph['text'])
                paragraph['image_ids']=[x for x in paragraph['image_ids'] if x.startswith('FRAME')]
        self.assertTrue(validate(article,[],[],self.frames,self.cfg)['pass'])
        article['sections'][0]['paragraphs'][0]['text']+=' [[SRC999]]'
        self.assertFalse(validate(article,[],[],self.frames,self.cfg)['pass'])

    def test_rubric_needs_real_quotes_and_both_independent_approvals(self):
        literary=self.review('literary');factual=self.review('factual')
        self.assertTrue(chief(self.work,self.article,literary,factual,0)['pass_editorial'])
        factual['scores'][0]['score']=9
        self.assertFalse(chief(self.work,self.article,literary,factual,1)['pass_editorial'])
        literary['scores'][0]['evidence'][0]['quote']='not in the article'
        self.assertFalse(review_gate(literary,self.article,'literary')['pass_editorial'])

    def test_independent_contexts_do_not_contain_each_others_reviews(self):
        save_json(self.work/'literary_review.json',{'private':'literary opinion'})
        save_json(self.work/'factual_review.json',{'private':'factual opinion'})
        for stage in ('literary','factual'):
            bundle=load_json(prepare_stage_context(self.work,stage))
            self.assertNotIn('literary_review.json',bundle)
            self.assertNotIn('factual_review.json',bundle)

    def test_ledger_does_not_promote_unknown_observations_or_objects(self):
        evidence=ledger(self.work,{'observations':[{'id':'O1','description':'Flying','frame_ids':['BAD']}]},
                        {'objects':[{'id':'X','name':'Unknown power-up','publishable':False}]},self.frames)
        self.assertEqual(evidence['facts'],[])

    def test_rewrite_cannot_drop_citations_or_media(self):
        changed=copy.deepcopy(self.article)
        changed['sections'][0]['paragraphs'][0]['text']='A new paragraph.'
        with self.assertRaises(ValueError):
            assert_preserved(self.article,changed,['sections[0].paragraphs[0]'])

    def test_localized_title_allowed_only_for_v2(self):
        vi=translated_fixture(self.article);vi['title']='Fixture Game: Nhịp chạy trong thành phố'
        self.assertFalse(validate_translation(self.article,vi)['pass'])
        self.assertTrue(validate_translation(self.article,vi,localize_title=True)['pass'])

    def test_brief_rejects_invented_fact_ids(self):
        brief={'core_identity':'Puzzle','central_tension':'Space','insights':[{'id':'I1','fact_ids':['MADEUP']}],
               'information_ownership':[],'sections':[],'research_filter':[]}
        with self.assertRaises(ValueError):
            retain_brief({'editorial_brief':brief},{'facts':[]},[])
