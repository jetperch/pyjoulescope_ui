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

"""Drive a Spectrum widget through the UI control socket.

Reads its state through the widget's automation methods
(``spectrum_info``, ``value_at``, ``spectrum_trace``, ``waterfall_column``).
See docs/plans/spectrum.md.
"""

import time


def open_widget(session, device, signal='i', **settings):
    """Open a Spectrum widget on device; return its unique id.

    :param settings: Widget settings to apply, such as fft_length=65536.
    """
    before = {i for i in session.enumerate('registry') if i.startswith('SpectrumWidget:')}
    session.publish('registry/view/actions/!widget_open', 'SpectrumWidget')
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        ids = [i for i in session.enumerate('registry')
               if i.startswith('SpectrumWidget:') and i not in before]
        if ids:
            widget = ids[0]
            session.publish_and_wait(f'registry/{widget}/settings/signal_stream_source', device.unique_id)
            configure(session, widget, signal=signal, **settings)
            return widget
        session.wait(0.2)
    raise AssertionError('Spectrum widget did not open')


def close_widget(session, widget):
    session.publish('registry/view/actions/!widget_close', widget)


def configure(session, widget, **settings):
    """Apply widget settings, each confirmed before returning."""
    for name, value in settings.items():
        session.publish_and_wait(f'registry/{widget}/settings/{name}', value)


def call(session, widget, method, *args):
    rsp = session.qt_action('call', path=widget, method=method, args=list(args))
    assert rsp.get('ok'), f'{method} failed: {rsp}'
    return rsp['result']


def info(session, widget):
    return call(session, widget, 'spectrum_info')


def wait_info(session, widget, predicate, timeout=15.0):
    """Poll spectrum_info until predicate(info) is true; return it."""
    deadline = time.monotonic() + timeout
    value = None
    while time.monotonic() < deadline:
        value = info(session, widget)
        if predicate(value):
            return value
        session.wait(0.25)
    raise AssertionError(f'spectrum condition not met: {value}')


def fresh(session, widget, count=20, timeout=30.0):
    """Clear, then wait for count new spectra; return spectrum_info.

    Call after changing the stimulus, so averages hold only the new signal.
    """
    session.publish(f'registry/{widget}/actions/!clear', None)
    session.wait(0.3)  # spectra already queued in the worker
    session.publish(f'registry/{widget}/actions/!clear', None)
    return wait_info(session, widget, lambda i: i.get('count', 0) >= count, timeout)


def value_at(session, widget, f, trace='average', search_bins=2):
    """[bin frequency, dB] of the largest trace value near f."""
    return call(session, widget, 'value_at', f, trace, search_bins)


def trace(session, widget, name='average'):
    """{f0, df, db} for a whole trace."""
    return call(session, widget, 'spectrum_trace', name)


def waterfall_column(session, widget, f, count=None):
    return call(session, widget, 'waterfall_column', f, count)
