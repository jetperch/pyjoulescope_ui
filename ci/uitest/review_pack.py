# Copyright 2026 Jetperch LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Build a translation review pack for a native speaker.

Uses the output of :mod:`uitest.display_audit`.  The pack is one folder
with an ``index.html`` that works offline: every screen, the English text
next to each translation shown on it, the open questions for the
language, and a comment box per screen.  The reviewer saves the comments
with one button and sends back the file.  Stage 7 of
docs/plans/translation_display_audit.md.

    python ci/uitest/review_pack.py --audit <audit dir> --lang de --out <dir>
"""

import argparse
import html
import json
import os
import shutil
import sys

_CI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.dirname(_CI)
if _CI not in sys.path:
    sys.path.insert(0, _CI)

from uitest import qt  # noqa: E402

LANGUAGE_NAMES = {
    'ar': 'Arabic', 'de': 'German', 'el': 'Greek', 'es': 'Spanish', 'fr': 'French',
    'it': 'Italian', 'ja': 'Japanese', 'ko': 'Korean', 'zh': 'Simplified Chinese',
}

# Open questions for reviewers.  See docs/plans/translation_followup.md.
QUESTIONS = {
    'ar': ['Is عناصر الواجهة right for the dockable panels named "Widgets"?',
           'Trigger is القدح and Waterfall is المخطط الشلالي.  Are these what you expect?',
           'Is the right-to-left layout correct on every screen?'],
    'de': ['Max Hold and Min Hold stay in English, as on R&S and Rigol analyzers.  OK?',
           '"Statistikfrequenz" or "Statistikrate" for the statistics update rate?'],
    'el': ['Widgets are γραφικά στοιχεία.  Is that natural for dockable panels?',
           'Span is Εύρος συχνοτήτων and Trigger is σκανδαλισμός.  OK?'],
    'es': ['Waterfall is "Cascada".  Would you prefer "Espectrograma"?',
           'Plugins are "Complementos".  OK?'],
    'fr': ['Hold is "Figer" and Max hold is "Maintien max".  OK?',
           '"Fréquence d\'échantillonnage" or "taux d\'échantillonnage"?'],
    'it': ['Markers are "marcatori".  Would you expect the loanword "marker"?',
           'Max hold and Min hold stay in English.  OK?'],
    'ja': ['The accumulator is 積算, as on power meters.  OK?',
           'Max hold is 最大値ホールド.  OK?'],
    'ko': ['The accumulator is 적산, as on power meters.  OK?',
           'Hold is 홀드 and Max hold is 최대 홀드.  OK?'],
    'zh': ['Span is 扫宽 and On/Off are 打开/关闭, as on Rigol and Siglent.  OK?',
           'Friendly name is 显示名称.  OK?'],
}

_STYLE = """
body{font:14px/1.45 system-ui,sans-serif;margin:0 auto;max-width:1100px;padding:16px;
     color:#1b1b1b;background:#fff}
h1{font-size:22px}h2{font-size:17px;margin-top:32px;border-top:1px solid #ccc;padding-top:16px}
img{max-width:100%;border:1px solid #999}
table{border-collapse:collapse;width:100%;margin:8px 0}
td,th{border:1px solid #ccc;padding:4px 6px;text-align:start;vertical-align:top}
th{background:#f2f2f2}textarea{width:100%;min-height:60px;font:inherit;box-sizing:border-box}
.bar{position:sticky;top:0;background:#fff;padding:8px 0;border-bottom:1px solid #ccc}
button{font:inherit;padding:6px 12px}
@media (prefers-color-scheme: dark){body{background:#1e1e1e;color:#e6e6e6}
 th{background:#2a2a2a}.bar{background:#1e1e1e}td,th{border-color:#444}}
"""

_SCRIPT = """
const KEY = 'joulescope_review_' + document.documentElement.lang;
function load() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
  document.querySelectorAll('textarea[data-screen]').forEach(t => {
    t.value = saved[t.dataset.screen] || '';
    t.addEventListener('input', save);
  });
}
function collect() {
  const out = {};
  document.querySelectorAll('textarea[data-screen]').forEach(t => {
    if (t.value.trim()) out[t.dataset.screen] = t.value;
  });
  return out;
}
function save() {
  try { localStorage.setItem(KEY, JSON.stringify(collect())); } catch (e) {}
}
function download() {
  const blob = new Blob([JSON.stringify({language: document.documentElement.lang,
                                         comments: collect()}, null, 1)],
                        {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'joulescope_ui_review_' + document.documentElement.lang + '.json';
  a.click();
}
document.addEventListener('DOMContentLoaded', load);
"""


def _catalog(locale):
    import polib
    path = os.path.join(_ROOT, 'joulescope_ui', 'locale', locale, 'LC_MESSAGES', 'joulescope_ui.po')
    reverse = {}
    for entry in polib.pofile(path):
        if not entry.obsolete and entry.msgstr:
            reverse.setdefault(entry.msgstr, entry.msgid)
    return reverse


def screen_strings(tree, reverse):
    """Return [(english, translation)] for catalog text shown on a screen."""
    out = []
    seen = set()
    for _, _, text in qt.iter_texts(tree):
        for line in [text] + text.split('\n'):
            line = line.strip()
            english = reverse.get(line)
            if english is not None and line not in seen:
                seen.add(line)
                out.append((english, line))
    return out


def build(audit_dir, locale, out_dir, size='1280x720'):
    """Write the review pack and return its index.html path."""
    src = os.path.join(audit_dir, locale)
    with open(os.path.join(src, 'report.json'), encoding='utf-8') as f:
        report = json.load(f)
    reverse = _catalog(locale)
    os.makedirs(os.path.join(out_dir, 'img'), exist_ok=True)
    name = LANGUAGE_NAMES.get(locale, locale)
    rtl = ' dir="rtl"' if locale == 'ar' else ''
    parts = [f'<!doctype html><html lang="{locale}"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             f'<title>Joulescope UI {html.escape(name)} review</title>',
             f'<style>{_STYLE}</style><script>{_SCRIPT}</script></head><body>',
             f'<h1>Joulescope UI: {html.escape(name)} translation review</h1>',
             '<div class="bar"><button onclick="download()">Save my comments to a file</button> '
             'Comments are kept in this browser while you work.  When done, save them and '
             'email the file back.</div>',
             '<p>Thank you for helping.  Each section below is one screen of the Joulescope UI '
             f'in {html.escape(name)}.  Please note anything that is wrong, unnatural, cut off, '
             'or still in English, and how you would say it.</p>']
    questions = QUESTIONS.get(locale)
    if questions:
        parts.append('<h2>Open questions</h2><ol>')
        parts += [f'<li>{html.escape(q)}</li>' for q in questions]
        parts.append('</ol><textarea data-screen="open_questions" '
                     'placeholder="Answers to the open questions"></textarea>')
    for r in report:
        if not r.get('image') or not r['image'].endswith(f'__{size}.png'):
            continue
        screen = r['screen']
        shutil.copy2(os.path.join(src, r['image']), os.path.join(out_dir, 'img', r['image']))
        tree_path = os.path.join(src, r['image'][:-4] + '.json')
        with open(tree_path, encoding='utf-8') as f:
            strings = screen_strings(json.load(f), reverse)
        parts.append(f'<h2 id="{html.escape(screen)}">{html.escape(screen)}</h2>')
        parts.append(f'<img loading="lazy" src="img/{html.escape(r["image"])}" alt="{html.escape(screen)}">')
        if strings:
            parts.append(f'<table><tr><th>English</th><th>{html.escape(name)}</th></tr>')
            parts += [f'<tr><td dir="ltr">{html.escape(e)}</td><td{rtl}>{html.escape(t)}</td></tr>'
                      for e, t in strings]
            parts.append('</table>')
        parts.append(f'<textarea data-screen="{html.escape(screen)}" placeholder="Comments"></textarea>')
    parts.append('<p><button onclick="download()">Save my comments to a file</button></p></body></html>')
    path = os.path.join(out_dir, 'index.html')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(parts))
    return path


def run(argv=None):
    p = argparse.ArgumentParser(description='Build a translation review pack.')
    p.add_argument('--audit', required=True, help='The display_audit output directory.')
    p.add_argument('--lang', action='append', required=True, help='Locale (repeat).')
    p.add_argument('--out', required=True, help='Output directory; one folder per locale.')
    args = p.parse_args(argv)
    for locale in args.lang:
        print(build(args.audit, locale, os.path.join(args.out, f'review_{locale}')))
    return 0


if __name__ == '__main__':
    sys.exit(run())
