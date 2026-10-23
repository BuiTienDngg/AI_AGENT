from __future__ import annotations
import html
import json
import re
import time
from pathlib import Path
from urllib.parse import quote, urlparse
import requests
from .core import canonical_url, public_url, save_json, trim, utc_now

USER_AGENT = 'GameSEOOfficeCodex/1.0 (local editorial research; automated fetch, no paid search)' 
HEADERS = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
COMMONS_API = 'https://commons.wikimedia.org/w/api.php'
WIKIPEDIA_API = 'https://en.wikipedia.org/w/api.php'
OPENALEX_API = 'https://api.openalex.org/works'


def get_json(url, params=None, timeout=20):
    last = None
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout, allow_redirects=True)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last = e
            if attempt < 2:
                time.sleep(1.0 + attempt * 1.5)
    raise RuntimeError(f'Web research request failed: {url}: {last}')


def plain(v):
    if isinstance(v, dict):
        v = v.get('value', '')
    s = html.unescape(re.sub(r'<[^>]+>', ' ', str(v or '')))
    return trim(s, 9000)


def academic_abstract(inverted_index):
    if not isinstance(inverted_index, dict) or not inverted_index:
        return ''
    positions = {}
    for word, indexes in inverted_index.items():
        for pos in indexes:
            positions[int(pos)] = word
    if not positions:
        return ''
    return trim(' '.join(positions[i] for i in sorted(positions)), 4500)


def search_wikipedia(query, limit=4, timeout=20):
    # Short concept names often have an exact page. Full-text search for a
    # long sentence can otherwise return unrelated pages containing its words.
    query = query.strip()
    if len(query.split()) <= 7 and not re.search(r'[:|"\n]', query):
        direct = get_json(WIKIPEDIA_API, {
            'action': 'query', 'format': 'json', 'titles': query,
            'prop': 'extracts|info', 'exintro': 1, 'explaintext': 1,
            'inprop': 'url', 'redirects': 1,
        }, timeout)
        exact = [p for p in direct.get('query', {}).get('pages', {}).values()
                 if 'missing' not in p and len(plain(p.get('extract', ''))) >= 130]
        if exact:
            page = exact[0]
            url = page.get('fullurl', '')
            if public_url(url):
                return [{'title': page['title'], 'url': canonical_url(url),
                         'excerpt': trim(plain(page['extract']), 2200),
                         'kind': 'encyclopedia', 'provider': 'Wikipedia', 'evidence_quality': 'overview'}]
    data = get_json(WIKIPEDIA_API, {
        'action': 'query', 'format': 'json', 'generator': 'search', 'gsrsearch': query,
        'gsrnamespace': 0, 'gsrlimit': limit, 'prop': 'extracts|info',
        'exintro': 1, 'explaintext': 1, 'inprop': 'url', 'redirects': 1,
    }, timeout)
    pages = sorted(data.get('query', {}).get('pages', {}).values(), key=lambda p: p.get('index', 999))
    result = []
    for p in pages:
        url = p.get('fullurl') or ('https://en.wikipedia.org/wiki/' + quote(p.get('title', '').replace(' ', '_')))
        excerpt = trim(plain(p.get('extract', '')), 2200)
        if len(excerpt) < 130 or not public_url(url):
            continue
        result.append({'title': p.get('title', ''), 'url': canonical_url(url), 'excerpt': excerpt,
                       'kind': 'encyclopedia', 'provider': 'Wikipedia', 'evidence_quality': 'overview'})
    return result


def search_openalex(query, limit=3, timeout=20):
    data = get_json(OPENALEX_API, {'search': query, 'per-page': limit}, timeout)
    results = []
    for w in data.get('results', []):
        title = plain(w.get('display_name', ''))
        abstract = trim(academic_abstract(w.get('abstract_inverted_index')), 2400)
        doi = w.get('doi', '')
        link = doi if public_url(doi) else w.get('id', '')
        if not (title and public_url(link)):
            continue
        results.append({'title': title, 'url': canonical_url(link), 'excerpt': abstract,
                        'year': w.get('publication_year'), 'kind': 'academic', 'provider': 'OpenAlex',
                        'evidence_quality': 'abstract' if len(abstract) >= 130 else 'metadata_only'})
    return results


def check_source_link(url, timeout=7):
    """Best-effort live link check; provider metadata remains the trusted discovery record.

    Paywalled academic publishers may block bots, so an HTTP 403 does not prove
    that a DOI or OpenAlex bibliographic entry was fabricated.
    """
    try:
        response = requests.head(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if response.status_code in (403, 405) or response.status_code >= 500:
            response = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True, stream=True)
            response.close()
        return {'http_status': int(response.status_code), 'http_reachable': 200 <= response.status_code < 400,
                'final_url': response.url if public_url(response.url) else '', 'checked_at': utc_now()}
    except requests.RequestException as error:
        return {'http_status': None, 'http_reachable': False, 'error': str(error)[:240], 'checked_at': utc_now()}


def source_queries(analysis, cfg):
    title = trim(analysis.get('game_title') or 'video game', 80)
    genre = trim(analysis.get('genre') or 'video game', 80)
    topics = [trim(x, 100) for x in analysis.get('research_topics', []) if isinstance(x, str)]
    topics = topics[:5]
    if cfg.get('editorial_profile')=='gameplay_first_v2':
        return list(dict.fromkeys([f'{title} game mechanics']+topics[:2])),[]
    queries = topics + [f'{genre} video game']
    if title.casefold() not in ('unknown game', 'video game'):
        queries.append(f'{title} game mechanics')
    # If relevant, Wikipedia provides general background; OpenAlex covers scholarly claims.
    return list(dict.fromkeys(queries))[:7], cfg['research_academic_queries'][:4]


def collect_text_sources(analysis, cfg, output_dir: Path):
    web_queries, academic_queries = source_queries(analysis, cfg)
    sources = []
    errors = []
    seen = set()
    max_sources = int(cfg['max_web_sources'])
    def register(entries):
        for e in entries:
            if len(sources) >= max_sources:
                break
            url = canonical_url(e.get('url', ''))
            if not url or not public_url(url) or url in seen:
                continue
            seen.add(url)
            e['id'] = f'SRC{len(sources) + 1:03}'
            e['url'] = url
            e['retrieved_at'] = utc_now()
            e['verified_metadata'] = True
            sources.append(e)
            if len(sources) >= max_sources:
                break
    for query in web_queries:
        if len(sources) >= min(max_sources, int(cfg.get('research_target_sources',3)) if cfg.get('editorial_profile')=='gameplay_first_v2' else int(cfg.get('min_text_sources',4))):
            break
        try:
            register(search_wikipedia(query, limit=3, timeout=cfg['network_timeout_seconds']))
        except Exception as e:
            errors.append({'provider': 'Wikipedia', 'query': query, 'error': str(e)})
    for query in academic_queries:
        try:
            register(search_openalex(query, limit=3, timeout=cfg['network_timeout_seconds']))
        except Exception as e:
            errors.append({'provider': 'OpenAlex', 'query': query, 'error': str(e)})
    # Give academic articles space even if wikipedia returned enough sources.
    # Check links without treating bot-blocked scholarly sites as non-existent.
    for source in sources:
        source['link_check'] = check_source_link(source['url'], timeout=min(7, cfg['network_timeout_seconds']))
    save_json(output_dir / 'sources.json', {'sources': sources, 'errors': errors, 'web_queries': web_queries,
                                              'academic_queries': academic_queries, 'created_at': utc_now()})
    if not sources and cfg.get('editorial_profile')!='gameplay_first_v2':
        raise RuntimeError('No web sources retrieved. Inspect sources.json errors; this workflow never invents sources.')
    return sources


def safe_license(extmeta):
    lic = plain(extmeta.get('LicenseShortName', '')).lower().replace(' ', '')
    license_url = plain(extmeta.get('LicenseUrl', ''))
    # Accept standard attribution/share-alike or public domain. Exclude NC/ND or unclear/custom.
    if ('-nc' in lic or '-nd' in lic or 'noncommercial' in lic or 'noderiv' in lic):
        return None
    if lic in ('cc0', 'cc0 1.0'.replace(' ', ''), 'publicdomain', 'pd', 'pd-old', 'pd-us') or 'public domain' in plain(extmeta.get('UsageTerms', '')).lower():
        return lic or 'Public Domain', license_url
    if re.fullmatch(r'cc-by(?:-sa)?(?:-\d+(?:\.\d+)?)?', lic) or ('creativecommons.org/licenses/by/' in license_url or 'creativecommons.org/licenses/by-sa/' in license_url):
        return lic or 'CC BY', license_url
    return None


def commons_search(query, limit=15, timeout=20):
    data = get_json(COMMONS_API, {'action': 'query', 'format': 'json', 'generator': 'search',
                                  'gsrsearch': query, 'gsrnamespace': 6, 'gsrlimit': limit,
                                  'prop': 'imageinfo', 'iiprop': 'url|extmetadata|size',
                                  'iiurlwidth': 1280, 'redirects': 1}, timeout)
    pages = sorted(data.get('query', {}).get('pages', {}).values(), key=lambda p: p.get('index', 999))
    out = []
    for p in pages:
        info = (p.get('imageinfo') or [{}])[0]
        ext = info.get('extmetadata') or {}
        license_info = safe_license(ext)
        original_url = info.get('url', '')
        if not license_info or not original_url.lower().split('?')[0].endswith(('.jpg', '.jpeg', '.png', '.webp')):
            continue
        # Use the API's standard-size thumbnail; original downloads can return 429.
        url = info.get('thumburl') or original_url
        if urlparse(url).hostname not in ('upload.wikimedia.org', 'thumb.wikimedia.org', 'commons.wikimedia.org'):
            continue
        sourcepage = info.get('descriptionurl', '')
        if not public_url(sourcepage):
            continue
        author = plain(ext.get('Artist', ''))
        if not author or len(author) > 260:
            continue
        out.append({'title': p.get('title', '').removeprefix('File:'), 'url': url,
                    'description': plain(ext.get('ImageDescription', '')),
                    'categories': plain(ext.get('Categories', '')),
                    'page_url': sourcepage, 'author': author, 'license': license_info[0],
                    'license_url': license_info[1],
                    'width': info.get('thumbwidth', info.get('width')), 'height': info.get('thumbheight', info.get('height')),
                    'original_url': original_url, 'original_bytes': info.get('size', 0),
                    'bytes': 0 if info.get('thumburl') else info.get('size', 0), 'search_query': query})
    return out


def commons_topic_match(img, query):
    """Require subject evidence, not search rank or generic color/style words.

    This is a conservative metadata screen, not a replacement for editorial QA.
    A licensed result can still be unrelated to the requested illustration.
    """
    ignored = {'a', 'an', 'the', 'of', 'and', 'in', 'on', 'with', 'for', 'photo', 'photos',
               'photograph', 'photographs', 'image', 'images', 'wikimedia', 'commons',
               'colorful', 'colourful', 'colored', 'coloured', 'bright', 'beautiful',
               'three', 'two', 'dimensional', 'real', 'world'}
    groups = {
        'tessellation': {'tessellation', 'tessellated', 'tiling', 'tile', 'tiles', 'mosaic'},
        'geometric': {'geometric', 'geometry', 'polygon', 'polygons'},
        'tile': {'tile', 'tiles', 'tiling', 'mosaic', 'ceramic'},
        'polyomino': {'polyomino', 'polyominoes', 'pentomino', 'pentominoes', 'tetromino', 'tetrominoes'},
        'train': {'train', 'trains', 'locomotive', 'railway', 'railroad'},
    }
    tokens = set(re.findall(r'[a-z]{3,}', query.casefold())) - ignored
    subject = ' '.join(str(img.get(key, '')) for key in ('title', 'description', 'categories')).casefold()
    words = set(re.findall(r'[a-z]{3,}', subject))
    matched = []
    for term in sorted(tokens):
        singular = term[:-1] if term.endswith('s') else term
        aliases = groups.get(term) or groups.get(singular) or {term, singular}
        if words & aliases:
            matched.append(term)
    required = min(2, len(tokens))
    accepted = bool(tokens) and len(matched) >= required
    return {'accepted': accepted, 'matched_terms': matched, 'required_matches': required,
            'score': len(matched), 'method': 'subject_metadata_match',
            'reason': '' if accepted else 'Insufficient concrete query subjects in title, description or categories'}


def download_commons_image(img, folder, timeout=20):
    if int(img.get('bytes') or 0) > 12 * 1024 * 1024:
        raise ValueError('Image exceeds 12 MB limit')
    url = img['url']
    host = urlparse(url).hostname
    if host not in ('upload.wikimedia.org', 'thumb.wikimedia.org'):
        raise ValueError('Unexpected image host')
    r = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
    r.raise_for_status()
    content_type = r.headers.get('Content-Type', '').lower()
    if not content_type.startswith('image/'):
        raise ValueError('Server did not return an image')
    folder.mkdir(parents=True, exist_ok=True)
    extension = Path(urlparse(url).path).suffix.lower()
    target = folder / (img['id'] + extension)
    size = 0
    with target.open('wb') as f:
        for chunk in r.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > 12 * 1024 * 1024:
                target.unlink(missing_ok=True)
                raise ValueError('Image exceeds 12 MB')
            f.write(chunk)
    from PIL import Image
    with Image.open(target) as im:
        im.verify()
    if extension == '.webp':
        # python-docx cannot reliably embed WEBP; transcode while retaining license metadata.
        from PIL import Image
        converted = folder / (img['id'] + '.jpg')
        with Image.open(target) as source:
            source.convert('RGB').save(converted, quality=92)
        target.unlink(missing_ok=True)
        target = converted
    img['path'] = str(target.resolve())
    return img


def collect_commons_images(analysis, cfg, output_dir: Path):
    # Keep discovery tied to this game. A railway fallback made puzzle articles
    # impossible to repair when the only second image was an unrelated train.
    topics = [trim(t, 85) for t in analysis.get('image_search_topics', []) if isinstance(t, str)][:5]
    if not topics:
        topics = [trim(t, 85) for t in analysis.get('research_topics', []) if isinstance(t, str)][:3]
    queries = list(dict.fromkeys(re.sub(r'^Wikimedia\s+Commons\s*[:\-]?\s*', '', topic, flags=re.I).strip()
                                for topic in topics if topic.strip()))
    target_count = cfg['commons_images']
    images, errors, used_pages = [], [], set()
    for q in list(dict.fromkeys(queries))[:8]:
        if len(images) >= target_count:
            break
        try:
            candidates = commons_search(q, timeout=cfg['network_timeout_seconds'])
            ranked = [(commons_topic_match(img, q), img) for img in candidates]
            ranked.sort(key=lambda entry: entry[0]['score'], reverse=True)
            for relevance, img in ranked:
                if img['page_url'] in used_pages:
                    continue
                if not relevance['accepted']:
                    errors.append({'query': q, 'image': img['page_url'],
                                   'reason': 'OFF_TOPIC_IMAGE', 'detail': relevance['reason']})
                    continue
                img['relevance'] = relevance
                img['id'] = f'IMG{len(images)+1:03}'
                try:
                    download_commons_image(img, output_dir / 'commons', timeout=cfg['network_timeout_seconds'])
                    images.append(img)
                    used_pages.add(img['page_url'])
                    break
                except Exception as error:
                    errors.append({'query': q, 'image': img.get('page_url'), 'error': str(error)})
        except Exception as error:
            errors.append({'query': q, 'error': str(error)})
    save_json(output_dir / 'images.json', {'images': images, 'errors': errors, 'queries': queries, 'created_at': utc_now()})
    if len(images) < target_count:
        raise RuntimeError(f'Only found {len(images)} of {target_count} relevant licensed Commons images. '
                           'Use short, game-relevant image_search_topics or research_plan.json image_queries, then resume. '
                           'See images.json for diagnostics; unrelated stock images are not substituted.')
    return images
