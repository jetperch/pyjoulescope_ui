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

"""Qt-free tests for uitest.stimulus: wiring discovery and DUT-input scaling."""

import json
import math
import types

import pytest

from uitest import stimulus


_WIRING = {
    'kind': 'adp3450', 'serial': 'SN:1',
    'connections': [
        {'source': 'W1', 'target': 'voltage', 'network': 'divider', 'ratio': 0.5},
        {'source': 'W2', 'target': 'current', 'network': 'series', 'ohms': 100},
    ],
}
_STATIONS = {'stations': {
    'bench': {'duts': [{'kind': 'js320', 'serial': 'JS320-8W2A', 'stimulus': _WIRING},
                       {'kind': 'js220', 'serial': 'JS220-000415'}]},
    'other': {'duts': [{'kind': 'js110'}]},
}}


def _device(unique_id):
    return types.SimpleNamespace(unique_id=unique_id, model=unique_id.split('-')[0])


@pytest.fixture
def clean_env(monkeypatch):
    for name in (stimulus.ENV, stimulus.ENV_FILE, stimulus.ENV_STATION):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_none_configured(clean_env):
    assert stimulus.wirings() == {}
    assert stimulus.wiring_for(_device('JS320-8W2A')) is None


def test_runner_env(clean_env):
    _, mod = stimulus.instruments()
    clean_env.setenv(stimulus.ENV, mod.encode({'JS320-8W2A': _WIRING}))
    assert stimulus.wiring_for(_device('JS320-8W2A')).serial == 'SN:1'
    assert stimulus.wiring_for(_device('JS220-000415')) is None


def test_stations_yaml_file(clean_env, tmp_path):
    yaml = pytest.importorskip('yaml')
    path = tmp_path / 'stations.yaml'
    path.write_text(yaml.safe_dump(_STATIONS))
    clean_env.setenv(stimulus.ENV_FILE, str(path))
    # only one station has a stimulus, so the station id is optional
    assert stimulus.wiring_for(_device('JS320-8W2A')).serial == 'SN:1'
    clean_env.setenv(stimulus.ENV_STATION, 'other')
    assert stimulus.wirings() == {}


def test_json_mapping_by_kind(clean_env, tmp_path):
    path = tmp_path / 'stimulus.json'
    path.write_text(json.dumps({'js320': _WIRING}))
    clean_env.setenv(stimulus.ENV_FILE, str(path))
    assert stimulus.wiring_for(_device('JS320-ABCD')) is not None


class _Adp:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *args, **kwargs: self.calls.append((name, args, kwargs))


def _stim():
    _, mod = stimulus.instruments()
    return stimulus.Stimulus(None, _device('JS320-8W2A'), mod.Wiring.from_dict(_WIRING), _Adp())


def test_sine_scales_to_dut_input():
    s = _stim()
    s.sine('voltage', 1000.0, 1.0)   # 1 V rms at the DUT through a 0.5 divider
    name, args, kwargs = s.adp.calls[-1]
    assert (name, args[0]) == ('wavegen_sine', 0)
    assert kwargs['vpp'] == pytest.approx(2 * 2 * math.sqrt(2))
    s.sine('current', 1000.0, 0.005)  # 5 mA rms nominal through 100 ohms
    assert s.adp.calls[-1][2]['vpp'] == pytest.approx(0.5 * 2 * math.sqrt(2))
    assert s.source_vrms('current', 0.005) == pytest.approx(0.5)


def test_out_of_range_skips():
    s = _stim()
    with pytest.raises(pytest.skip.Exception, match='above'):
        s.sine('voltage', 1000.0, 5.0)
    with pytest.raises(pytest.skip.Exception, match='resolution'):
        s.sine('voltage', 1000.0, 0.001)
    with pytest.raises(pytest.skip.Exception, match='not wired'):
        s.require('gpi0')
    with pytest.raises(pytest.skip.Exception, match='divider'):
        s.require('voltage', networks=('direct',))
