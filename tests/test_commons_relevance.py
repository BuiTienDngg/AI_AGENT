import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from game_seo.core import ROOT, load_json
from game_seo.research import collect_commons_images, commons_search, commons_topic_match


class CommonsRelevanceTests(unittest.TestCase):
    def test_license_and_color_keywords_do_not_make_onfray_art_relevant(self):
        image = {'title':'Michel Onfray 64 - 2023.jpg', 'license':'ccby-sa4.0',
                 'description':'Anniversary card, painted letters and graphical wordplay in identical glyphs.',
                 'categories':'Colorful paintings|Ambigrams of Michel Onfray|Painted patterns'}
        self.assertFalse(commons_topic_match(image, 'colorful tessellation')['accepted'])
        self.assertFalse(commons_topic_match(image, 'geometric mosaic pattern')['accepted'])

    def test_concrete_mosaic_and_tiling_metadata_matches(self):
        image = {'title':'Central Pavement with Geometric Pattern Mosaic.jpg',
                 'description':'House of the Doves in Pompeii', 'categories':'Roman mosaics'}
        self.assertTrue(commons_topic_match(image, 'geometric mosaic pattern')['accepted'])
        self.assertTrue(commons_topic_match(image, 'colorful tessellation')['accepted'])

    def test_generic_style_or_one_weak_word_is_not_enough(self):
        self.assertFalse(commons_topic_match({'title':'Beautiful colorful image'}, 'colorful beautiful photo')['accepted'])
        self.assertFalse(commons_topic_match({'title':'Random geometric portrait'}, 'geometric mosaic pattern')['accepted'])

    def test_collector_continues_after_off_topic_result_instead_of_counting_it(self):
        cfg = load_json(ROOT / 'config.json')
        def image(title):
            return {'title':title, 'page_url':'https://commons.wikimedia.org/wiki/File:'+title,
                    'license':'ccby-sa4.0','description':title,'categories':''}
        results = [[image('Geometric tile mosaic')], [image('Michel Onfray anniversary')],
                   [image('Roman geometric mosaic pattern')]]
        def download(img, folder, timeout):
            img['path'] = str(Path(folder) / (img['id'] + '.jpg'))
        with tempfile.TemporaryDirectory() as folder, \
             patch('game_seo.research.commons_search', side_effect=results) as search, \
             patch('game_seo.research.download_commons_image', side_effect=download):
            found = collect_commons_images({'image_search_topics':[
                'geometric tile mosaic','colorful tessellation','geometric mosaic pattern']}, cfg, Path(folder))
            registry = load_json(Path(folder) / 'images.json')
        self.assertEqual(search.call_count, 3)
        self.assertEqual(len(found), 2)
        self.assertFalse(any('Onfray' in img['title'] for img in found))
        self.assertTrue(any(row.get('reason') == 'OFF_TOPIC_IMAGE' for row in registry['errors']))

    def test_search_exposes_plain_description_and_categories_for_screening(self):
        raw = {'query':{'pages':{'1':{'title':'File:Example.jpg','imageinfo':[{
            'url':'https://upload.wikimedia.org/a/Example.jpg',
            'descriptionurl':'https://commons.wikimedia.org/wiki/File:Example.jpg',
            'width':800,'height':600,'extmetadata':{
                'LicenseShortName':{'value':'CC BY-SA 4.0'},
                'LicenseUrl':{'value':'https://creativecommons.org/licenses/by-sa/4.0/'},
                'Artist':{'value':'Photographer'},
                'ImageDescription':{'value':'<p>Roman geometric mosaic</p>'},
                'Categories':{'value':'Ancient mosaics|Geometric patterns'}}}]}}}}
        with patch('game_seo.research.get_json', return_value=raw):
            result = commons_search('geometric mosaic')
        self.assertEqual(result[0]['description'], 'Roman geometric mosaic')
        self.assertIn('Ancient mosaics', result[0]['categories'])


if __name__ == '__main__':
    unittest.main()
