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

"""Capture every UI screen in every language for the display audit.

For each language and window size, this launches the UI, visits the
screens in :data:`SCREENS`, and saves a screenshot, the widget tree, and a
report of truncated text and untranslated text.  It then writes an HTML
contact sheet with the languages side by side.  See
docs/plans/translation_display_audit.md.

Run from the ``pyjoulescope_ui/`` directory::

    python ci/uitest/display_audit.py --out <dir> [--lang de --lang qps]
        [--hide-usb] [--screens views,widgets,...] [--device]

``--hide-usb`` re-runs this script under ``bwrap`` (Linux) with USB hidden,
so the UI cannot open the instruments attached to a bench machine.
"""

import argparse
import html
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time

_CI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.dirname(_CI)
if _CI not in sys.path:
    sys.path.insert(0, _CI)

from uitest import assets, pseudo_locale, qt  # noqa: E402

_log = logging.getLogger('display_audit')
LOCALES = ['en', 'qps', 'ar', 'de', 'el', 'es', 'fr', 'it', 'ja', 'ko', 'zh']
SIZES = [(1280, 720), (1920, 1080)]
_SCREEN = (2560, 1600)
_JLS = 'js110_evk1_10s_0_7_0.jls'
_SETTLE = 1.0
_TAG = re.compile(r'<[^<>]+>')
_HTML_SKIP = re.compile(r'<(head|style|script)\b.*?</\1>|<!DOCTYPE[^>]*>', re.S | re.I)
# Help pages whose body is English by design; only their title is checked.
_ENGLISH_BODY = {'help_changelog', 'help_credits'}
# The Apache license notice in About stays English, as legal text.
_LEGAL = ('Copyright ', 'License', 'WARRANTIES', '"AS IS"', 'applicable law')

# Text that is the same in every language: names, units, and identifiers.
_KEEP = re.compile(
    r'^(?:[\W\d_]*|None|Python|\d+\.\d+.*|(?:Linux|Windows|macOS|Darwin)-\S+|.*\b(?:Joulescope|JS110|JS220|JS320|JLS|USB|USBET|CSV|FFT|PSD|UTC|GPI|GPO|'
    r'OpenGL|vsync|Inferno|Viridis|SignalRecordConfig|StatisticsRecordConfig)\b.*|'
    r'[a-z0-9_]+(?:/[A-Za-z0-9_]+)*|Jetperch LLC|[A-Za-z]+:\d+|[\w.-]+\.(?:jls|csv|json|txt|log)|'
    r'https?://\S+|(?:[A-Za-z]:)?[/\\].*|\S*\{\w+\}\S*)$')


class Catalog:
    """Look up translations, and find English text that should be translated."""

    def __init__(self, locale):
        import polib
        self.locale = locale
        self.expected = set()
        self._tr = {}
        self._translations = set()
        if locale in ('en', pseudo_locale.LOCALE):
            return
        path = os.path.join(_ROOT, 'joulescope_ui', 'locale', locale, 'LC_MESSAGES', 'joulescope_ui.po')
        for entry in polib.pofile(path):
            if entry.obsolete or entry.msgctxt or not entry.msgstr:
                continue
            self._tr[entry.msgid] = entry.msgstr
            self._translations.add(entry.msgstr)
            if entry.msgstr != entry.msgid:
                self.expected.add(entry.msgid)

    def tr(self, text):
        """Translate English UI text, as the UI shows it in this locale."""
        if self.locale == pseudo_locale.LOCALE:
            return pseudo_locale.pseudo(text)
        return self._tr.get(text, text)

    def untranslated(self, text):
        """Return True if the text is shown in English but should not be.

        Markup, such as the HTML tooltips, is removed and each line is
        checked on its own.
        """
        text = _HTML_SKIP.sub('\n', text)
        for line in _TAG.sub('\n', text).split('\n'):
            line = html.unescape(line).strip()
            if not line or _KEEP.match(line) or any(x in line for x in _LEGAL):
                continue
            if self.locale == pseudo_locale.LOCALE:
                if not pseudo_locale.is_marked(line):
                    return True
            elif line in self._translations:
                continue  # such as French "Exporter" for "Export", also an English msgid
            elif line in self.expected or line.rstrip(':').strip() in self.expected:
                return True
        return False


# -- screens --------------------------------------------------------------

def _new_ids(session, before, prefix=None):
    now = set(session.enumerate('registry'))
    return sorted(i for i in now - before if prefix is None or i.startswith(prefix))


def _root_name(session):
    root = session.qt_inspect(max_depth=0)
    return root.get('class'), root.get('objectName')


def _find(session, path, timeout=5.0):
    """Wait for a widget path, such as ``@LocaleDialog``, to resolve."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return session.qt_inspect(path=path, max_depth=0)
        except Exception:
            if time.monotonic() >= deadline:
                return None
        session.wait(0.2)


def _close(session, path):
    """Close a dialog, then wait for it to go away."""
    for method in ('reject', 'close'):
        if _find(session, path, timeout=0) is None:
            return
        try:
            session.qt_action('call', path=path, method=method)
        except Exception:
            pass
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and _find(session, path, timeout=0) is not None:
            session.wait(0.2)


class Audit:
    """Visit screens for one language and record the results."""

    # Dialog name: (class, how to open it)
    DIALOGS = {
        'dialog_language': ('LocaleDialog', ('publish', 'registry/ui/actions/!locale_dialog', None)),
        'dialog_report_issue': ('ReportIssueDialog', ('menu', 'Help', 'Report Issue')),
        'dialog_view_manager': ('ViewManagerDialog', ('menu', 'View', 'Manage')),
        'dialog_event_analyzer': ('EventAnalyzerDialog', ('menu', 'Tools', 'Event Analyzer (alpha)')),
        'dialog_signal_record': ('SignalRecordConfigDialog',
                                 ('publish', 'registry/app/settings/signal_stream_record', True)),
        'dialog_statistics_record': ('StatisticsRecordConfigDialog',
                                     ('publish', 'registry/app/settings/statistics_stream_record', True)),
    }
    RANGE_DIALOGS = {
        'HistogramRangeTool': 'HistogramRangeToolDialog',
        'CdfRangeTool': 'CdfRangeToolDialog',
        'FrequencyRangeTool': 'FrequencyRangeToolDialog',
        'MaxWindowRangeTool': 'MaxWindowDialog',
        'exporter': 'ExporterDialog',
    }
    SKIP_WIDGETS = {'ExampleWidget', 'settings', 'ProfileWidget', 'PubSubExplorerWidget',
                    'PublishSpyWidget', 'TimesyncWidget'}

    def __init__(self, session, locale, size, out_dir, catalog):
        self.s = session
        self.locale = locale
        self.size = size
        self.out_dir = out_dir
        self.catalog = catalog
        self.results = []
        self._audit_view = False
        self._jls = None

    def capture(self, screen, path=''):
        """Save the screenshot, tree, and findings for the current screen."""
        tag = f'{screen}__{self.size[0]}x{self.size[1]}'
        self.s.wait(_SETTLE)
        tree = self.s.qt_inspect(path=path, max_depth=80)
        with open(os.path.join(self.out_dir, tag + '.png'), 'wb') as f:
            f.write(self.s.qt_screenshot(path=path))
        with open(os.path.join(self.out_dir, tag + '.json'), 'w', encoding='utf-8') as f:
            json.dump(tree, f, ensure_ascii=False)
        texts = list(qt.iter_texts(tree))
        if screen in _ENGLISH_BODY:
            texts = [t for t in texts if t[1] == 'windowTitle']
        english = sorted({t for _, kind, t in texts if kind != 'toolTip' and self.catalog.untranslated(t)})
        tooltips = sorted({t for _, kind, t in texts if kind == 'toolTip' and self.catalog.untranslated(t)})
        self.results.append({'screen': screen, 'size': list(self.size), 'image': tag + '.png',
                             'truncated': qt.find_truncation(tree), 'untranslated': english,
                             'untranslated_tooltips': tooltips, 'blank': qt.find_blank_buttons(tree)})

    def run(self, name, fn):
        try:
            fn()
        except Exception as ex:
            _log.exception('%s %s failed', self.locale, name)
            self.results.append({'screen': name, 'size': list(self.size), 'error': str(ex)})

    def _menu(self, *path):
        self.s.menubar_invoke('/'.join(self.catalog.tr(p) for p in path))

    # views

    def views(self):
        for view in ['multimeter', 'oscilloscope']:
            self.run(f'view_{view}', lambda v=view: (self.s.set_view(v), self.capture(f'view_{v}')))
        self.run('view_file', lambda: (self._open_jls(), self.capture('view_file')))

    def _open_jls(self):
        self.s.set_view('file')
        if self._jls is None:
            self._jls = self.s.open_file(assets.get_asset(_JLS))
            self.s.wait(2.0)
        return self._jls

    # widgets and their settings

    def widgets(self, device=False):
        if not self._audit_view:
            self.s.publish('registry/view/actions/!add', 'view:audit')
            self._audit_view = True
            self.s.wait(0.5)
        classes = self.s.query('registry_manager/capabilities/widget.class/list') or []
        for cls in classes:
            if cls not in self.SKIP_WIDGETS:
                self.run(f'widget_{cls}', lambda c=cls: self._widget(c))

    def _open_widget(self, cls):
        before = set(self.s.enumerate('registry'))
        self.s.publish('registry/view/actions/!widget_open', cls)
        self.s.wait(1.0)
        return _new_ids(self.s, before, prefix=cls + ':')

    def _widget(self, cls):
        self.s.set_view('audit')
        ids = self._open_widget(cls)
        try:
            self.capture(f'widget_{cls}')
            for unique_id in ids[:1]:
                settings = self._open_widget('settings')
                try:
                    for settings_id in settings[:1]:
                        self.s.publish(f'registry/{settings_id}/settings/target', unique_id)
                        self.capture(f'settings_{cls}')
                finally:
                    for settings_id in settings:
                        self.s.publish('registry/view/actions/!widget_close', settings_id)
        finally:
            for unique_id in ids:
                self.s.publish('registry/view/actions/!widget_close', unique_id)
            self.s.wait(0.5)

    # dialogs

    def _dialog(self, name, cls, opener):
        kind = opener[0]
        if kind == 'publish':
            self.s.publish(opener[1], opener[2])
        elif kind == 'menu':
            self._menu(*opener[1:])
        else:
            opener[1]()
        path = '@' + cls
        if _find(self.s, path) is None:
            raise RuntimeError(f'{name}: {cls} did not open')
        try:
            self.capture(name, path)
        finally:
            _close(self.s, path)

    def dialogs(self):
        self.s.set_view('oscilloscope')
        for page in ['getting_started', 'changelog', 'credits', 'about']:
            self.run(f'help_{page}', lambda p=page: self._dialog(
                f'help_{p}', 'HelpHtmlMessageBox', ('publish', 'registry/help_html/actions/!show', p)))
        for name, (cls, opener) in self.DIALOGS.items():
            self.run(name, lambda n=name, c=cls, o=opener: self._dialog(n, c, o))
        self.s.publish('registry/app/settings/signal_stream_record', False)
        self.s.publish('registry/app/settings/statistics_stream_record', False)

    # range tools and context menus on the JLS waveform

    def range_tools(self):
        self.run('range_tools', self._range_tools)

    def _range_tools(self):
        self._open_jls()
        waveform = self.s.waveform()
        x_range = self.s.subrange(waveform, 0.45, 0.55)
        for tool in self.s.query('registry_manager/capabilities/range_tool.class/list') or []:
            cls = self.RANGE_DIALOGS.get(tool)
            if cls is None:
                continue
            self.run(f'range_{tool}', lambda t=tool, c=cls: self._dialog(
                f'range_{t}', c, ('publish', f'registry/{waveform}/actions/!range_tool',
                                  {'tool': t, 'x_range': x_range})))

    # device screens: read-only, no firmware, calibration, fuse, or power changes

    def device(self):
        self.run('device', self._device)

    def _device(self):
        deadline = time.monotonic() + 15.0
        devices = []
        while time.monotonic() < deadline and not devices:
            devices = [d for d in self.s.devices() if not d.unique_id.endswith('-UPDATER')]
            self.s.wait(0.5)
        if not devices:
            raise RuntimeError('no device')
        for d in devices:
            self.s.wait_for_statistics(d.unique_id)
        self.s.set_view('multimeter')
        self.s.wait(2.0)
        self.capture('device_multimeter_live')
        if not self._audit_view:
            self.s.publish('registry/view/actions/!add', 'view:audit')
            self._audit_view = True
        self.s.set_view('audit')
        ids = self._open_widget('DeviceControlWidget')
        try:
            self.capture('device_control_live')
            self.run('device_info', lambda: self._dialog(
                'device_info', 'DeviceInfoDialog', ('call', lambda: self.s.qt_action(
                    'call', path='@Js220CtrlWidget', method='_on_info'))))
        finally:
            for unique_id in ids:
                self.s.publish('registry/view/actions/!widget_close', unique_id)
        for d in devices:
            settings = self._open_widget('settings')
            try:
                for settings_id in settings[:1]:
                    self.s.publish(f'registry/{settings_id}/settings/target', d.unique_id)
                    self.capture(f'device_settings_{d.model}')
            finally:
                for settings_id in settings:
                    self.s.publish('registry/view/actions/!widget_close', settings_id)

    def context_menus(self):
        self.run('context_menus', self._context_menus)

    def _context_menus(self):
        self._open_jls()
        waveform = self.s.waveform()
        geo = self.s.plot_geometry(waveform)
        if not geo:
            raise RuntimeError('no plot geometry')
        _, _, w, h = geo
        spots = {'plot': (w // 2, h // 3), 'x_axis': (w // 2, 5), 'y_axis': (5, h // 3)}
        for name, (px, py) in spots.items():
            self.s.right_click(waveform, px, py)
            self.s.wait(0.5)
            texts = [t for t in self.s.menu_items() if isinstance(t, str)]
            english = sorted({part for t in texts for part in t.split('/')
                              if self.catalog.untranslated(part)})
            self.results.append({'screen': f'menu_{name}', 'size': list(self.size),
                                 'menu': texts, 'truncated': [], 'untranslated': english,
                                 'untranslated_tooltips': []})
            self.s.qt_action('menu_close')
            self.s.wait(0.3)


# -- driver ---------------------------------------------------------------

_GROUPS = ('views', 'widgets', 'dialogs', 'range_tools', 'context_menus')


def run_locale(locale, out_root, groups, sizes, locale_path, device=False, executable=None):
    """Capture all screens for one language.

    :param executable: The UI executable, or None for ``python -m joulescope_ui``.
    :return: The list of screen results.
    """
    from uitest.harness import UiSession
    out_dir = os.path.join(out_root, locale)
    os.makedirs(out_dir, exist_ok=True)
    home = os.path.join(out_root, '_home', locale)
    shutil.rmtree(home, ignore_errors=True)
    os.makedirs(os.path.join(home, '.joulescope'))
    if locale != 'en':
        with open(os.path.join(home, '.joulescope', 'language.txt'), 'w') as f:
            f.write(locale)
    home_prev = os.environ.get('HOME')
    os.environ['HOME'] = home  # uitest.discover finds server.json from HOME
    env = {'HOME': home, 'JOULESCOPE_UI_LOCALE_PATH': locale_path,
           'LANG': 'en_US.UTF-8' if locale == 'en' else os.environ.get('LANG', 'C.UTF-8')}
    catalog = Catalog(locale)
    results = []
    try:
        for size in sizes:
            with UiSession(executable, offscreen=True, offscreen_size=_SCREEN, env=env, cwd=_ROOT,
                           config_clear_on_exit=False) as session:
                session.resize_window_settled(*size)
                audit = Audit(session, locale, size, out_dir, catalog)
                for group in groups + (['device'] if device else []):
                    fn = getattr(audit, group)
                    fn(device) if group == 'widgets' else fn()
                results.extend(audit.results)
    finally:
        if home_prev is None:
            os.environ.pop('HOME', None)
        else:
            os.environ['HOME'] = home_prev
    with open(os.path.join(out_dir, 'report.json'), 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    return results


def write_html(out_root, locales):
    """Write the contact sheet and the summary."""
    reports = {}
    for locale in locales:
        path = os.path.join(out_root, locale, 'report.json')
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                reports[locale] = json.load(f)
    rows = {}
    for locale, report in reports.items():
        for r in report:
            key = (r['screen'], tuple(r['size']))
            rows.setdefault(key, {})[locale] = r
    out = ['<!doctype html><meta charset="utf-8"><title>Display audit</title>',
           '<style>body{font:13px sans-serif;margin:16px}td{vertical-align:top;padding:4px}'
           'img{width:320px;border:1px solid #888}.bad{color:#b00}.ok{color:#080}'
           'th{position:sticky;top:0;background:#fff}</style>',
           '<h1>Display audit</h1>', _summary_html(reports), '<table><tr><th>Screen</th>']
    out += [f'<th>{html.escape(loc)}</th>' for loc in reports]
    out.append('</tr>')
    for (screen, size), by_locale in sorted(rows.items()):
        out.append(f'<tr><td><b>{html.escape(screen)}</b><br>{size[0]}×{size[1]}</td>')
        for locale in reports:
            r = by_locale.get(locale)
            if r is None:
                out.append('<td></td>')
                continue
            cell = []
            if r.get('image'):
                src = f'{locale}/{r["image"]}'
                cell.append(f'<a href="{src}"><img loading="lazy" src="{src}"></a>')
            if r.get('error'):
                cell.append(f'<div class="bad">error: {html.escape(r["error"])}</div>')
            for t in r.get('truncated', []):
                cell.append(f'<div class="bad">✂ {html.escape(t["text"])} ({t["need"]}>{t["have"]})</div>')
            for t in r.get('untranslated', []):
                cell.append(f'<div class="bad">EN: {html.escape(t)}</div>')
            for t in r.get('blank', []):
                cell.append(f'<div class="bad">blank button: {html.escape(t)}</div>')
            for t in r.get('menu', []) or []:
                cell.append(f'<div>{html.escape(t)}</div>')
            out.append('<td>' + ''.join(cell) + '</td>')
        out.append('</tr>')
    out.append('</table>')
    path = os.path.join(out_root, 'index.html')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))
    return path


def summarize(reports):
    """Count findings per locale: {locale: {screens, errors, truncated, untranslated}}."""
    out = {}
    for locale, report in reports.items():
        out[locale] = {
            'screens': len(report),
            'errors': sum(1 for r in report if r.get('error')),
            'truncated': sum(len(r.get('truncated', [])) for r in report),
            'untranslated': sum(len(r.get('untranslated', [])) for r in report),
            'untranslated_tooltips': sum(len(r.get('untranslated_tooltips', [])) for r in report),
            'blank': sum(len(r.get('blank', [])) for r in report),
        }
    return out


def _summary_html(reports):
    rows = ['<table><tr><th>Locale</th><th>Screens</th><th>Errors</th><th>Truncated</th>'
            '<th>English text</th><th>English tooltips</th><th>Blank buttons</th></tr>']
    for locale, c in summarize(reports).items():
        rows.append(f'<tr><td>{locale}</td><td>{c["screens"]}</td><td>{c["errors"]}</td>'
                    f'<td>{c["truncated"]}</td><td>{c["untranslated"]}</td>'
                    f'<td>{c["untranslated_tooltips"]}</td><td>{c["blank"]}</td></tr>')
    rows.append('</table>')
    return ''.join(rows)


def _hide_usb_reexec(argv):
    """Re-run under bwrap with the USB device tree hidden."""
    bwrap = shutil.which('bwrap')
    if bwrap is None:
        raise SystemExit('--hide-usb needs bwrap (Linux)')
    args = [a for a in argv if a != '--hide-usb']
    cmd = [bwrap, '--dev-bind', '/', '/', '--tmpfs', '/dev/bus/usb',
           '--tmpfs', '/sys/bus/usb/devices', sys.executable] + args
    return subprocess.call(cmd)


def parser_config():
    p = argparse.ArgumentParser(description='Capture UI screens in every language.')
    p.add_argument('--out', required=True, help='Output directory.')
    p.add_argument('--lang', action='append', help=f'Locale (repeat).  Default: {" ".join(LOCALES)}')
    p.add_argument('--screens', default=','.join(_GROUPS), help='Comma-separated screen groups.')
    p.add_argument('--size', action='append', help='WIDTHxHEIGHT (repeat).  Default: 1280x720, 1920x1080')
    p.add_argument('--hide-usb', action='store_true', help='Hide USB devices from the UI (Linux, bwrap).')
    p.add_argument('--device', action='store_true', help='Also capture device screens (bench).')
    p.add_argument('--html-only', action='store_true', help='Rebuild index.html from existing reports.')
    return p


def run(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    args = parser_config().parse_args(argv)
    if args.hide_usb:
        return _hide_usb_reexec([os.path.abspath(__file__)] + argv)
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    locales = args.lang or LOCALES
    out_root = os.path.abspath(args.out)
    os.makedirs(out_root, exist_ok=True)
    if not args.html_only:
        groups = [g for g in args.screens.split(',') if g]
        sizes = [tuple(int(x) for x in s.split('x')) for s in args.size] if args.size else SIZES
        locale_path = os.path.join(out_root, '_locale')
        pseudo_locale.generate(os.path.join(_ROOT, 'joulescope_ui', 'locale', 'joulescope_ui.pot'),
                               locale_path)
        for locale in locales:
            _log.info('locale %s', locale)
            run_locale(locale, out_root, groups, sizes, locale_path, device=args.device)
    path = write_html(out_root, locales)
    reports = {}
    for locale in locales:
        p = os.path.join(out_root, locale, 'report.json')
        if os.path.isfile(p):
            with open(p, encoding='utf-8') as f:
                reports[locale] = json.load(f)
    for locale, c in summarize(reports).items():
        print(f'{locale:4s} screens={c["screens"]} errors={c["errors"]} truncated={c["truncated"]} '
              f'english={c["untranslated"]} english_tooltips={c["untranslated_tooltips"]} blank={c["blank"]}')
    print(path)
    return 0


if __name__ == '__main__':
    sys.exit(run())
