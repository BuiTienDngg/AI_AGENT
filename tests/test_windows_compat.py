from pathlib import Path
import tempfile
import unittest
from PIL import Image
from game_seo.core import ROOT, load_json
from game_seo.runner import codex_call
from game_seo.research import commons_search, download_commons_image
from game_seo.export import export_all
from test_pipeline import translated_fixture
from test_pipeline import fixtures


class WindowsCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.article, self.sources, self.images, self.frames = fixtures(self.folder)
        self.cfg = {**load_json(ROOT / 'config.json'),'editorial_profile':'legacy'}

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_jpeg_without_jfif_or_exif_exports_to_word(self):
        from docx import Document
        from docx.image.exceptions import UnrecognizedImageError
        from docx.image.image import Image as DocxImage

        path = Path(self.images[0]['path'])
        original = path.read_bytes()
        self.assertEqual(original[2:4], b'\xff\xe0')
        segment_size = int.from_bytes(original[4:6], 'big')
        without_jfif = original[:2] + original[4 + segment_size:]
        path.write_bytes(without_jfif)
        with Image.open(path) as valid_image:
            valid_image.verify()
        with self.assertRaises(UnrecognizedImageError):
            DocxImage.from_file(str(path))

        files = export_all(self.article, self.sources, self.images, self.frames,
                           self.folder, translation_vi=translated_fixture(self.article))
        self.assertEqual(len(Document(files['docx_en']).inline_shapes), 6)
        self.assertEqual(len(Document(files['docx_vi']).inline_shapes), 6)
        self.assertEqual(path.read_bytes(), without_jfif)
        self.assertFalse((self.folder / 'output' / 'assets').exists())

    def test_commons_thumbnail_download_preserves_attribution(self):
        import io
        from unittest.mock import Mock, patch

        original = 'https://upload.wikimedia.org/wikipedia/commons/a/ab/Photo.jpg'
        thumbnail = 'https://thumb.wikimedia.org/wikipedia/commons/thumb/a/ab/Photo.jpg/1280px-Photo.jpg'
        info = {'url': original, 'thumburl': thumbnail, 'width': 8000, 'height': 4000,
                'thumbwidth': 1280, 'thumbheight': 640, 'size': 20000000,
                'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Photo.jpg',
                'extmetadata': {'LicenseShortName': {'value': 'CC BY-SA 4.0'},
                                'LicenseUrl': {'value': 'https://creativecommons.org/licenses/by-sa/4.0/'},
                                'Artist': {'value': 'Fixture Photographer'}}}
        metadata = {'query': {'pages': {'1': {'title': 'File:Photo.jpg', 'imageinfo': [info]}}}}
        payload = io.BytesIO()
        Image.new('RGB', (1280, 640)).save(payload, format='JPEG')
        response = Mock(headers={'Content-Type': 'image/jpeg'})
        response.iter_content.return_value = [payload.getvalue()]
        with patch('game_seo.research.get_json', return_value=metadata), patch('game_seo.research.requests.get', return_value=response) as fetch:
            image = commons_search('photo')[0]
            image['id'] = 'IMG001'
            downloaded = download_commons_image(image, self.folder)
        self.assertEqual(fetch.call_args.args[0], thumbnail)
        self.assertEqual(downloaded['original_url'], original)
        self.assertEqual(downloaded['author'], 'Fixture Photographer')
        self.assertEqual(downloaded['license_url'], info['extmetadata']['LicenseUrl']['value'])
        self.assertEqual(downloaded['page_url'], info['descriptionurl'])
        with Image.open(downloaded['path']) as result:
            self.assertEqual(result.size, (1280, 640))


    def test_codex_image_prompt_is_a_positional_argument(self):
        import argparse
        from types import SimpleNamespace
        from unittest.mock import patch

        # Match the CLI's variadic image option to catch prompts consumed as filenames.
        parser = argparse.ArgumentParser()
        for flag in ('--cd', '--sandbox', '--output-schema', '--output-last-message'):
            parser.add_argument(flag)
        parser.add_argument('--skip-git-repo-check', action='store_true')
        parser.add_argument('--json', action='store_true')
        parser.add_argument('--image', nargs='+', action='append')
        parser.add_argument('prompt', nargs='?')
        parser.add_argument('--model')
        image_paths = [self.frames['frames'][i]['path'] for i in range(2)]

        def execute(command, **kwargs):
            args = parser.parse_args(command[2:])
            self.assertIsNotNone(args.prompt)
            self.assertIn('Analyze the attached contact sheet', args.prompt)
            self.assertEqual([path for group in args.image for path in group], image_paths)
            Path(args.output_last_message).write_text('{}', encoding='utf-8')
            return SimpleNamespace(returncode=0, stdout='', stderr='')

        with patch('game_seo.runner.shutil.which', return_value='codex'), patch('game_seo.runner.subprocess.run', side_effect=execute):
            self.assertEqual(codex_call('analyze', self.folder, self.cfg, image_paths=image_paths), {})

