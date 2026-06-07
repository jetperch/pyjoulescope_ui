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

"""HIL bench registry.

The farm is heterogeneous: each bench runs a different OS and has a different
set of Joulescopes attached.  Rather than assume a device is present, every
station *advertises* its platform and attached device models.  Tests then:

* **skip** a device test when the station does not advertise that model, and
* **fail** when an advertised device is unexpectedly absent at runtime.

Configuration lives in ``stations.toml`` (loaded with stdlib ``tomllib``).  The
active station is chosen by the ``JS_UITEST_STATION`` environment variable, or
by matching the machine hostname, falling back to a ``[stations.default]`` entry.
"""

import dataclasses
import os
import socket
import tomllib


_STATIONS_TOML = os.path.join(os.path.dirname(__file__), 'stations.toml')

#: Device models the suite understands (upper-case, matching discover.Device.model).
KNOWN_MODELS = ('JS220', 'JS320', 'JS110')

ENV_STATION = 'JS_UITEST_STATION'
#: Point at a different stations registry (a bench/CI runner keeps its own,
#: instead of editing the committed ``stations.toml``).
ENV_STATIONS_FILE = 'JS_UITEST_STATIONS_FILE'


@dataclasses.dataclass(frozen=True)
class Station:
    """A single HIL bench and the capabilities it advertises."""

    name: str
    platform: str = ''            # 'windows' | 'windows_arm64' | 'macos' | 'ubuntu'
    host: str = ''                # hostname; '' matches by name/env only
    devices: tuple = ()           # advertised device models, e.g. ('JS220', 'JS320')
    notes: str = ''

    def advertises(self, model):
        """True if this station claims a device of ``model`` is attached."""
        return model.upper() in self.devices


def _normalize(name, raw):
    devices = tuple(str(m).upper() for m in raw.get('devices', []))
    unknown = [m for m in devices if m not in KNOWN_MODELS]
    if unknown:
        raise ValueError(f'station {name!r}: unknown device models {unknown}')
    return Station(
        name=name,
        platform=str(raw.get('platform', '')),
        host=str(raw.get('host', '')),
        devices=devices,
        notes=str(raw.get('notes', '')),
    )


def load_stations(path=None):
    """Load the station registry as ``{name: Station}``.

    The path defaults to ``$JS_UITEST_STATIONS_FILE`` when set, else the
    committed ``stations.toml``.
    """
    path = path or os.environ.get(ENV_STATIONS_FILE) or _STATIONS_TOML
    with open(path, 'rb') as f:
        data = tomllib.load(f)
    return {name: _normalize(name, raw) for name, raw in data.get('stations', {}).items()}


def current_station(stations=None, hostname=None):
    """Resolve the active station for this machine.

    Resolution order: ``JS_UITEST_STATION`` env var (by name) -> hostname match
    -> a station literally named ``'default'`` -> None.
    """
    if stations is None:
        stations = load_stations()
    env_name = os.environ.get(ENV_STATION)
    if env_name:
        if env_name not in stations:
            raise KeyError(f'{ENV_STATION}={env_name!r} not found in stations registry')
        return stations[env_name]
    hostname = hostname or socket.gethostname()
    for station in stations.values():
        if station.host and station.host.lower() == hostname.lower():
            return station
    return stations.get('default')
