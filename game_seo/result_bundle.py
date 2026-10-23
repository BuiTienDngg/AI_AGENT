"""Publish-ready copies of approved Word documents and the figures they use."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image

from .core import slugify, save_json


def figures(article):
    from .export import image_caption
    number = 0
    for section in article.get('sections', []):
        groups = [(section['heading'], section.get('paragraphs', []))]
        groups.extend((s['heading'], s.get('paragraphs', [])) for s in section.get('subsections', []))
        for heading, paragraphs in groups:
            for paragraph in paragraphs:
                for ref in paragraph.get('image_ids', []):
                    number += 1
                    yield {'figure': number, 'id': ref, 'heading': heading,
                           'caption': image_caption(paragraph, ref, heading)}


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def inside_file(path, root):
    path = Path(path)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('Result source is missing or outside the current run: ' + path.name)
    return path


def csv_value(value):
    value = str(value or '')
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value


def build_result(article, translation, images, frame_manifest, files, workdir):
    """Copy exact document/image bytes. Never rewrite article prose or call AI."""
    work = Path(workdir).resolve()
    result = work / 'result'
    if result.is_symlink() or result.resolve().parent != work:
        raise ValueError('result must be a local folder, not a symbolic link.')
    en, vi = list(figures(article)), list(figures(translation))
    if [row['id'] for row in en] != [row['id'] for row in vi]:
        raise ValueError('EN/VI figure order does not match.')
    registry = {row['id']: row for row in images}
    frames = {row['frame_id']: row for row in frame_manifest.get('frames', [])}
    with tempfile.TemporaryDirectory(prefix='.result-', dir=work) as temporary:
        staging = Path(temporary)
        (staging / 'images').mkdir()
        manifest = {'version': 1, 'documents': {}, 'images': [], 'placements': []}
        for key in ('docx_en', 'docx_vi'):
            source = inside_file(files[key], work)
            if source.suffix.lower() != '.docx':
                raise ValueError('Result documents must be Word files.')
            target = staging / source.name
            shutil.copy2(source, target)
            manifest['documents'][key] = {'file': source.name, 'sha256': digest(target)}
        names = {}
        for english, vietnamese in zip(en, vi):
            ref = english['id']
            meta = registry.get(ref) or frames.get(ref)
            if meta is None:
                raise ValueError('Unregistered result image: ' + ref)
            if ref not in names:
                source = inside_file(meta.get('path', ''), work)
                if ref in registry and any(not meta.get(key) for key in ('author', 'license', 'page_url')):
                    raise ValueError('Image attribution is incomplete: ' + ref)
                with Image.open(source) as image:
                    extension = {'JPEG':'.jpg', 'PNG':'.png', 'WEBP':'.webp', 'GIF':'.gif',
                                 'TIFF':'.tif', 'BMP':'.bmp'}.get(image.format)
                    if extension is None:
                        raise ValueError('Unsupported result image format: ' + ref)
                    width, height = image.size
                label = unicodedata.normalize('NFKD', english['caption'].replace('đ','d').replace('Đ','D'))
                label = ''.join(c for c in label if not unicodedata.combining(c))
                name = f"{len(names)+1:02d}-{slugify(label)[:60]}{extension}"
                relative = 'images/' + name
                shutil.copy2(source, staging / relative)
                names[ref] = relative
                manifest['images'].append({
                    'id':ref, 'file':relative, 'sha256':digest(staging/relative),
                    'width':width, 'height':height,
                    'kind':'wikimedia_commons' if ref in registry else 'gameplay',
                    'caption_en':english['caption'], 'caption_vi':vietnamese['caption'],
                    'author':meta.get('author','') if ref in registry else 'Slope3 gameplay capture',
                    'license':meta.get('license','') if ref in registry else 'Owner-supplied gameplay',
                    'license_url':meta.get('license_url',''), 'source_url':meta.get('page_url',''),
                    'source_title':meta.get('title','')})
            manifest['placements'].append({
                'figure':english['figure'], 'id':ref, 'file':names[ref],
                'heading_en':english['heading'], 'heading_vi':vietnamese['heading'],
                'caption_en':english['caption'], 'caption_vi':vietnamese['caption']})
        by_id = {row['id']:row for row in manifest['images']}
        columns = ['figure','file','heading_en','caption_en','heading_vi','caption_vi',
                   'author','license','source_url','license_url']
        with (staging/'image_names.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer = csv.DictWriter(stream,fieldnames=columns)
            writer.writeheader()
            for row in manifest['placements']:
                combined = {**by_id[row['id']],**row}
                writer.writerow({key:csv_value(combined.get(key,'')) for key in columns})
        credits = ['IMAGE CREDITS / NGUỒN ẢNH', '',
                   'Keep Commons attribution and license links when publishing.',
                   'Giữ tên tác giả, nguồn và link giấy phép khi đăng ảnh Commons.', '']
        for row in manifest['images']:
            credits.extend([row['file'], 'EN: '+row['caption_en'], 'VI: '+row['caption_vi'],
                            'Author: '+row['author'], 'License: '+row['license'],
                            'Source: '+row['source_url'], 'License URL: '+row['license_url'], ''])
        (staging/'IMAGE_CREDITS.txt').write_text('\n'.join(credits),encoding='utf-8')
        save_json(staging/'result_manifest.json',manifest)
        previous = None
        if (result/'result_manifest.json').is_file():
            try:
                previous = json.loads((result/'result_manifest.json').read_text(encoding='utf-8'))
            except (OSError,ValueError):
                pass
        tracked = [*manifest['documents'].values(),*manifest['images']]
        if previous == manifest and all(
            (result/row['file']).is_file() and not (result/row['file']).is_symlink() and
            digest(result/row['file'])==row['sha256'] for row in tracked) and all(
                (result/name).is_file() and digest(result/name)==digest(staging/name)
                for name in ('image_names.csv','IMAGE_CREDITS.txt')):
            return result
        archive = None
        if result.exists():
            archive = work/'result_history'/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
            archive.parent.mkdir(exist_ok=True)
            os.replace(result,archive)
        try:
            os.replace(staging,result)
        except Exception:
            if archive and not result.exists():
                os.replace(archive,result)
            raise
    return result
