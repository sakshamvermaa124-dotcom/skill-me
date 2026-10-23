"""
Stamp every local .js/.css reference in the HTML pages with a hash of the file's content:

    <script src="theme.js?v=3f9c2a1b">   <link href="/home.css?v=8d0e4c77">

Run from the repo root after editing any JS/CSS (and before deploying):

    python bump_versions.py          # rewrite the HTML
    python bump_versions.py --check  # exit 1 if any page is out of date (used by the pre-commit hook)

Unchanged files keep the same version, so browsers keep them cached; vercel.json can then
cache JS/CSS for a year (immutable). config.js is versioned too but is still served
no-cache, because it is the one file that must change without an HTML edit.
"""
import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REF = re.compile(r'((?:src|href)=")(/?)([A-Za-z0-9_-]+\.(?:js|css))(?:\?v=[^"]*)?(")')


def file_hash(name, cache={}):
    if name not in cache:
        path = os.path.join(ROOT, name)
        if not os.path.isfile(path):
            cache[name] = None
        else:
            with open(path, 'rb') as f:
                cache[name] = hashlib.sha256(f.read()).hexdigest()[:10]
    return cache[name]


def stamp(match):
    prefix, slash, name, quote = match.groups()
    h = file_hash(name)
    if h is None:  # not a local file (or missing): leave the reference alone
        return match.group(0)
    return f'{prefix}{slash}{name}?v={h}{quote}'


def main():
    check = '--check' in sys.argv
    stale = []
    for page in sorted(f for f in os.listdir(ROOT) if f.endswith('.html')):
        path = os.path.join(ROOT, page)
        with open(path, encoding='utf-8', newline='') as f:
            content = f.read()
        updated = REF.sub(stamp, content)
        if updated != content:
            stale.append(page)
            if not check:
                with open(path, 'w', encoding='utf-8', newline='') as f:
                    f.write(updated)
                print(f'Updated {page}')
    if check and stale:
        print('Asset versions are out of date in: ' + ', '.join(stale))
        sys.exit(1)


if __name__ == '__main__':
    main()
