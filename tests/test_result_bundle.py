import copy
import csv
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from game_seo.admin_web import create_app
from game_seo.core import load_json,save_json
from game_seo.export import export_all
from game_seo.result_bundle import build_result,digest
from test_pipeline import fixtures,translated_fixture


class ResultTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.work=Path(self.temp.name)/'runs'/'game-date'
        self.article,self.sources,self.images,self.frames=fixtures(self.work)
        self.article['sections'][0]['paragraphs'][0]['image_captions']=[{'image_id':'IMG001','caption':'Mosaic patterns'}]
        self.vi=translated_fixture(self.article)
        self.files=export_all(self.article,self.sources,self.images,self.frames,self.work,translation_vi=self.vi)

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_docx_and_used_images_with_bilingual_caption_mapping(self):
        result=self.work/'result';manifest=load_json(result/'result_manifest.json')
        self.assertEqual(len(list(result.glob('*.docx'))),2)
        self.assertEqual(len(manifest['images']),6)
        self.assertEqual(len(list((result/'images').iterdir())),6)
        for key,source in self.files.items():
            self.assertEqual(digest(source),digest(result/manifest['documents'][key]['file']))
        self.assertEqual(manifest['images'][0]['file'],'images/01-mosaic-patterns.jpg')
        for row in manifest['images']:
            original=next((m for m in self.images if m['id']==row['id']),None) or next(f for f in self.frames['frames'] if f['frame_id']==row['id'])
            self.assertEqual(digest(original['path']),digest(result/row['file']))
        with (result/'image_names.csv').open(encoding='utf-8-sig',newline='') as stream:
            rows=list(csv.DictReader(stream))
        self.assertEqual(rows[0]['caption_en'],'Mosaic patterns')
        self.assertTrue(rows[0]['caption_vi'])
        self.assertIn(self.images[0]['license_url'],(result/'IMAGE_CREDITS.txt').read_text(encoding='utf-8'))

    def test_rebuild_is_idempotent_and_changed_result_is_archived(self):
        build_result(self.article,self.vi,self.images,self.frames,self.files,self.work)
        self.assertFalse((self.work/'result_history').exists())
        (self.work/'result'/'IMAGE_CREDITS.txt').write_text('manual edit',encoding='utf-8')
        build_result(self.article,self.vi,self.images,self.frames,self.files,self.work)
        archives=list((self.work/'result_history').iterdir())
        self.assertEqual(len(archives),1)
        self.assertEqual((archives[0]/'IMAGE_CREDITS.txt').read_text(),'manual edit')

    def test_repeated_ids_are_copied_once_and_unused_registry_images_are_omitted(self):
        article=copy.deepcopy(self.article)
        article['sections'][0]['paragraphs'][1]['image_ids']=['IMG001']
        vi=translated_fixture(article)
        build_result(article,vi,self.images,self.frames,self.files,self.work)
        manifest=load_json(self.work/'result/result_manifest.json')
        self.assertEqual(len(manifest['images']),5)
        self.assertEqual(len(manifest['placements']),6)
        self.assertNotIn('IMG002',[r['id'] for r in manifest['images']])
        self.assertEqual(manifest['placements'][0]['file'],manifest['placements'][1]['file'])

    def test_missing_or_outside_image_preserves_previous_result(self):
        original=(self.work/'result/result_manifest.json').read_bytes()
        bad=copy.deepcopy(self.images);bad[0]['path']=str(Path(self.temp.name)/'outside.jpg')
        Path(bad[0]['path']).write_bytes(b'not-an-image')
        with self.assertRaises(ValueError):
            build_result(self.article,self.vi,bad,self.frames,self.files,self.work)
        self.assertEqual((self.work/'result/result_manifest.json').read_bytes(),original)

    def test_zip_download_contains_docs_images_and_credits_but_no_run_internals(self):
        save_json(self.work/'export_manifest.json',{'files':self.files})
        app=create_app(Path(self.temp.name)/'data',self.work.parent)
        client=app.test_client()
        response=client.get('/api/runs/game-date/result.zip')
        self.assertEqual(response.status_code,200)
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            names=archive.namelist()
            self.assertEqual(sum(n.endswith('.docx') for n in names),2)
            self.assertEqual(sum(n.startswith('result/images/') for n in names),6)
            self.assertIn('result/IMAGE_CREDITS.txt',names)
            self.assertFalse(any('admin_config' in n or 'auth' in n for n in names))
        self.assertTrue(client.get('/api/state').json['history'][0]['result_available'])
        manifest=load_json(self.work/'result/result_manifest.json')
        manifest['images'][0]['file']='../../outside.txt'
        save_json(self.work/'result/result_manifest.json',manifest)
        self.assertEqual(client.get('/api/runs/game-date/result.zip').status_code,404)
