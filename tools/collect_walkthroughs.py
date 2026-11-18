"""Prepare public guide downloads and index their local evidence coverage.

Downloads stay under ignored out/logic-research. This script performs no network
requests: run the generated curl config with network permission, then index it.
A matching page or a chest mention is evidence availability, never route approval.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urljoin, urlsplit, urldefrag
from urllib.robotparser import RobotFileParser

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT / 'out/logic-research'
HOST = 'https://zeldacentral.com'
PREFIX = '/games/breath-of-the-wild/'
NAME_ALIASES = {'To Quoma Shrine': 'To Quomo Shrine'}  # Local Manual typo; English completion catalog uses Quomo.
SECTIONS = ('shrines/', 'walkthrough/', 'shrine-quests/', 'dlc/', 'divine-beasts/')


class Article(HTMLParser):
    def __init__(self, fallback_main=False):
        super().__init__()
        self.fallback_main = fallback_main
        self.depth = 0
        self.active = None
        self.active_tag = None
        self.skip = 0
        self.links, self.images, self.parts = set(), set(), []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.depth += 1
        if self.active is None and ('entry-content' in attrs.get('class', '').split() or attrs.get('id') == 'partiePrincipale' or (self.fallback_main and tag == 'main')):
            self.active = self.depth
            self.active_tag = tag
        if self.active is None:
            return
        if tag in ('script', 'style', 'noscript'):
            self.skip += 1
        if tag == 'a' and 'href' in attrs:
            self.links.add(attrs['href'])
        if tag == 'img':
            for attr in ('src', 'data-src'):
                if attrs.get(attr):
                    self.images.add(attrs[attr])
        if tag in ('p', 'li', 'h1', 'h2', 'h3', 'h4', 'br', 'tr'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            return
        if tag in ('script', 'style', 'noscript') and self.skip:
            self.skip -= 1
        if self.active == self.depth and tag == self.active_tag:
            self.active = None
        self.depth = max(0, self.depth - 1)

    def handle_data(self, data):
        if self.active is not None and not self.skip:
            self.parts.append(data)

    @property
    def text(self):
        return '\n'.join(line for part in ''.join(self.parts).splitlines()
                         if (line := re.sub(r'\s+', ' ', part).strip()))


def read(path):
    return json.loads(path.read_text())


def name_key(name):
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    return re.sub('[^a-z0-9]', '', name.lower())


def parse(path):
    result = Article()
    html = path.read_text(errors='replace')
    result.feed(html)
    if not result.text:
        result = Article(fallback_main=True)
        result.feed(html)
    return result


def prepare():
    robots = RobotFileParser()
    robots.parse((COLLECTION / 'zeldacentral-robots.txt').read_text().splitlines())
    requests_path = COLLECTION / 'requests.json'
    requests = read(requests_path) if requests_path.exists() else {}
    for path in COLLECTION.glob('zeldaspalace-chapter-*.html'):
        chapter = int(path.stem.rsplit('-', 1)[1])
        requests[f'https://www.zeldaspalace.com/breathofthewild/soluce.php?p={chapter}'] = path.name
    urls = set(requests)
    for path in [*COLLECTION.glob('*-index.html'), *COLLECTION.glob('pages/*.html')]:
        for link in parse(path).links:
            url = urldefrag(urljoin(HOST, link))[0]
            parts = urlsplit(url)
            if parts.netloc != 'zeldacentral.com' or parts.query:
                continue
            if any(parts.path.startswith(PREFIX + section) for section in SECTIONS):
                if robots.can_fetch('BotWAPRouteResearch', url):
                    urls.add(url)
    if len(urls) > 500:
        raise ValueError('Unexpectedly broad crawl; inspect discovered URLs before continuing')
    for url in sorted(urls):
        slug = urlsplit(url).path.removeprefix(PREFIX).strip('/').replace('/', '--') or 'index'
        requests.setdefault(url, 'pages/' + slug + '--' + hashlib.sha256(url.encode()).hexdigest()[:10] + '.html')
    pending = [(url, filename) for url, filename in sorted(requests.items())
               if not (COLLECTION / filename).exists()]
    config = ['rate = "1/s"']
    for i, (url, filename) in enumerate(pending):
        if i:
            config.append('next')
        config.extend(['location', 'fail', 'silent', 'show-error', 'max-time = 30',
                       'user-agent = "BotWAPRouteResearch/1.0"',
                       'url = ' + json.dumps(url), 'output = ' + json.dumps(str(COLLECTION / filename)),
                       'write-out = "%{url_effective} %{http_code}\\n"'])
    requests_path.write_text(json.dumps(requests, indent=2) + '\n')
    (COLLECTION / 'downloads.curl').write_text('\n'.join(config) + '\n')
    print(f'{len(requests)} discovered pages; {len(pending)} pending downloads.')


def index():
    manifest = []
    requests = read(COLLECTION / 'requests.json')
    textdir = COLLECTION / 'text'
    textdir.mkdir(exist_ok=True)
    for url, filename in sorted(requests.items()):
        path = COLLECTION / filename
        record = {'url': url, 'html': filename, 'status': 'missing'}
        if path.exists():
            article = parse(path)
            text = article.text
            if re.search(r'<title>\s*(?:One moment|Just a moment)', path.read_text(errors='replace'), re.I):
                record['status'] = 'blocked_challenge'
            elif len(text) < 200:
                record['status'] = 'invalid_or_empty_article'
            else:
                textfile = 'text/' + path.stem + '.txt'
                (COLLECTION / textfile).write_text(text + '\n')
                record.update(status='downloaded', text=textfile,
                              sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                              saved_utc=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                              words=len(text.split()), chest_mentions=len(re.findall(r'\bchests?\b', text, re.I)),
                              screenshot_urls=sorted(article.images))
        manifest.append(record)
    by_shrine = {name_key(urlsplit(row['url']).path.rstrip('/').split('/')[-1]): row
                 for row in manifest if '/shrines/' in row['url'] and row['status'] == 'downloaded'}
    manual = read(ROOT / 'worlds/botw/data/manual/locations.json')['data']
    shrine_names = sorted({e['name'] for e in manual if e['name'].endswith(' Shrine')})
    shrine_coverage = []
    for name in shrine_names:
        source = by_shrine.get(name_key(NAME_ALIASES.get(name, name)))
        shrine_coverage.append({'name': name, 'reference_name': NAME_ALIASES.get(name, name), 'source': source['url'] if source else None,
                               'text': source['text'] if source else None,
                               'chest_mentions': source.get('chest_mentions', 0) if source else 0,
                               'status': 'reference_available' if source else 'missing_reference',
                               'route_verified': False, 'gameplay_verified': False})
    shrine_by_name = {row['name']: row for row in shrine_coverage}
    chest_catalog = read(ROOT / 'worlds/botw/data/chests.json')
    route_path = ROOT / 'worlds/botw/static/chest_routes.json'
    routes = {row['check_id']: row for row in read(route_path)['routes']} if route_path.exists() else {}
    physical = {}
    object_sources = []
    for path in sorted(COLLECTION.glob('object-map-*-chests.json')):
        objects = read(path)
        object_sources.append({'file': path.name, 'objects': len(objects),
                               'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        for obj in objects:
            key = (obj['map_type'], obj['map_name'], obj['hash_id'])
            physical.setdefault(key, []).append(obj)
    chest_coverage = []
    included_ids = {entry['id'] for entry in chest_catalog['locations']}
    for entry in [*chest_catalog['locations'], *chest_catalog.get('ignored', [])]:
        shrine = entry['name'].split(' - Chest', 1)[0]
        source = shrine_by_name.get(shrine)
        parts = entry['logical_map'].split('/')
        matches = physical.get((parts[1], parts[2], entry['hash_id']), [])
        exact = matches[0] if len(matches) == 1 else None
        object_url = (f"https://radar.zeldamods.org/obj/{parts[1]}/{parts[2]}/{entry['hash_id']}" if exact else None)
        chest_coverage.append({'object_reference': object_url, 'object_id': exact['objid'] if exact else None,
                               'id': entry['id'], 'name': entry['name'],
                               'logical_map': entry['logical_map'], 'hash_id': f"{entry['hash_id']:08X}",
                               'research_route': routes.get(entry['id']), 'bound': bool(entry.get('region')), 'catalog_included': entry['id'] in included_ids,
                               'excluded_reason': entry.get('reason'), 'requires': entry.get('requires', ''),
                               'reference': source['source'] if source else None,
                               'status': ('research_established_route' if entry['id'] in routes else
                                          'shrine_reference_requires_actor_match' if source and source['source'] else 'missing_exact_route_reference'),
                               'route_verified': False, 'gameplay_verified': False})
    report = {'summary': {'downloaded_pages': sum(r['status'] == 'downloaded' for r in manifest),
                          'failed_pages': sum(r['status'] != 'downloaded' for r in manifest),
                          'shrines': len(shrine_names), 'shrines_with_references': sum(r['source'] is not None for r in shrine_coverage),
                          'shrine_pages_with_chest_mentions': sum(r['chest_mentions'] > 0 for r in shrine_coverage),
                          'discovered_chests': len(chest_catalog['locations']),
                          'excluded_chests': len(chest_catalog.get('ignored', [])),
                          'object_source_records': sum(source['objects'] for source in object_sources), 'bound_chests': sum(r['bound'] for r in chest_coverage),
                          'chests_with_shrine_page': sum(bool(r['reference']) for r in chest_coverage),
                          'chests_with_object_match': sum(bool(r['object_reference']) for r in chest_coverage),
                          'bound_chests_with_object_match': sum(r['bound'] and bool(r['object_reference']) for r in chest_coverage),
                          'research_established_routes': sum(bool(row['research_route']) for row in chest_coverage),
                          'gameplay_verified_routes': 0},
              'shrines': shrine_coverage, 'chests': chest_coverage,
              'binding_warnings': chest_catalog.get('binding_warnings', []),
              'object_sources': object_sources, 'name_aliases': NAME_ALIASES,
              'limits': ['Downloaded walkthroughs are secondary evidence, not gameplay tests.',
                         'Shrine references do not identify individual chest HashIds without a physical match.',
                         'Overworld chest positions are not route instructions.',
                         'Images are referenced by original URL, not downloaded.',
                         'Nintendo guide is introductory, not a complete every-chest walkthrough.']}
    (COLLECTION / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (COLLECTION / 'coverage.json').write_text(json.dumps(report, indent=2) + '\n')
    # Keyword differences are a review queue, never inferred mandatory gates.
    candidates = []
    rule_sources = [*chest_catalog['locations'], *read(ROOT / 'worlds/botw/static/completions.json')['locations']]
    capabilities = {'Magnesis': r'\bmagnesis\b', 'Cryonis': r'\bcryonis\b',
                    'Progressive Stasis': r'\bstasis\b', 'Progressive Remote Bomb': r'\b(?:remote )?bombs?\b',
                    'Paraglider': r'\b(?:paraglider|paraglid(?:e|ing))\b'}
    for entry in rule_sources:
        shrine = entry['name'].split(' - Chest', 1)[0]
        ref = shrine_by_name.get(shrine)
        if not entry.get('region') or not ref or not ref['text']:
            continue
        text = (COLLECTION / ref['text']).read_text()
        for item, pattern in capabilities.items():
            if item not in entry.get('requires', '') and re.search(pattern, text, re.I):
                candidates.append({'check': entry['name'], 'id': entry['id'], 'capability_mentioned': item,
                                   'guide': ref['source'], 'text': ref['text'],
                                   'status': 'needs_manual_review_not_a_proven_requirement'})
    (COLLECTION / 'audit-candidates.json').write_text(json.dumps(candidates, indent=2) + '\n')
    print(json.dumps(report['summary'], indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'index'])
    args = parser.parse_args()
    COLLECTION.mkdir(parents=True, exist_ok=True)
    (COLLECTION / 'pages').mkdir(exist_ok=True)
    (prepare if args.action == 'prepare' else index)()
