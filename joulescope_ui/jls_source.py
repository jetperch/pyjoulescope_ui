# Copyright 2022-2023 Jetperch LLC
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

from joulescope_ui import CAPABILITIES, Metadata, register, get_topic_name, get_instance
from joulescope_ui.jls_v1 import JlsV1
from joulescope_ui.jls_v2 import JlsV2
from joulescope_ui.jls_v2_annotations import load as annotations_load
import glob
import logging
import os
import queue
import re
import threading


_V1_PREFIX = bytes([0xd3, 0x74, 0x61, 0x67, 0x66, 0x6d, 0x74, 0x20, 0x0d, 0x0a, 0x20, 0x0a, 0x20, 0x20, 0x1a, 0x1c])
_V2_PREFIX = bytes([0x6a, 0x6c, 0x73, 0x66, 0x6d, 0x74, 0x0d, 0x0a, 0x20, 0x0a, 0x20, 0x1a, 0x20, 0x20, 0xb2, 0x1c])
_log = logging.getLogger(__name__)


def _jls_version_detect(filename):
    """Detect the JLS version.

    :param filename: The JLS filename.
    :return: 1 or 2
    """
    if hasattr(filename, 'read') and hasattr(filename, 'seek'):
        d = filename.read(16)
        filename.seek(0)
    else:
        with open(filename, 'rb') as f:
            d = f.read(16)
    if d == _V2_PREFIX:
        return 2
    elif d == _V1_PREFIX:
        return 1
    else:
        raise RuntimeError('unsupported file prefix')


class _Dedup:
    """A deduplicating FIFO dict.

    A normal dict with popitem would work, but popitem
    operates in LIFO order.  This implementation ensures
    FIFO order by using a separate list to keep key order.

    See https://docs.python.org/3/library/stdtypes.html?highlight=popitem#dict.popitem
    """

    def __init__(self):
        self._dict = {}
        self._order = []

    def __len__(self):
        return len(self._order)

    def insert(self, key, value):
        if key not in self._dict:
            self._order.append(key)
        self._dict[key] = value

    def pop(self):
        key = self._order.pop(0)
        return self._dict.pop(key)


@register
class JlsSource:
    CAPABILITIES = []
    SETTINGS = {}

    def __init__(self, path=None):
        self._queue = queue.Queue()

        if path is not None:
            name = os.path.basename(os.path.splitext(path)[0])
            path = os.path.abspath(path)
            if not os.path.isfile(path):
                raise ValueError(f'File not found: {path}')
        else:
            name = 'JlsSource'

        self.SETTINGS = {
            'name': {
                'dtype': 'str',
                'brief': 'The name for this JLS stream buffer source',
                'default': name,
            },
            'path': {
                'dtype': 'str',
                'brief': 'The file path.',
                'default': path,
            },
            'notes': {
                'dtype': 'str',
                'brief': 'The user notes.',
                'default': '',
            },
        }
        self._jls = None
        self.pubsub = None
        self.CAPABILITIES = [CAPABILITIES.SOURCE, CAPABILITIES.SIGNAL_BUFFER_SOURCE]
        self._thread = None

    def on_pubsub_register(self):
        topic = get_topic_name(self)
        pubsub = self.pubsub
        path = pubsub.query(f'{topic}/settings/path')
        _log.info(f'jls_source register {topic}')
        pubsub.topic_remove(f'{topic}/settings/sources')
        pubsub.topic_remove(f'{topic}/settings/signals')
        pubsub.topic_add(f'{topic}/settings/sources', Metadata('node', 'Sources', flags=['hide', 'ro', 'skip_undo']))
        pubsub.topic_add(f'{topic}/settings/signals', Metadata('node', 'Signals', flags=['hide', 'ro', 'skip_undo']))
        jls_version = _jls_version_detect(path)
        try:
            if jls_version == 2:
                _log.info('jls_source v2')
                self._jls = JlsV2(path, pubsub, topic)
            elif jls_version == 1:
                _log.info('jls_source v1')
                self._jls = JlsV1(path, pubsub, topic)
            else:
                raise ValueError(f'Unsupported JLS version {jls_version}')
        except Exception as ex:
            pubsub.publish('registry/ui/actions/!error_msg', f'Could not load JLS file\n{path}\n{ex}')

        pubsub.publish('registry/paths/actions/!mru_load', path)
        self._thread = threading.Thread(target=self.run)
        self._thread.start()

    def on_pubsub_unregister(self):
        self.close()

    def run(self):
        do_quit = False
        requests = _Dedup()
        while not do_quit:
            timeout = 0.0 if len(requests) else 2.0
            try:
                cmd, value = self._queue.get(timeout=timeout)
            except queue.Empty:
                if len(requests):
                    value = requests.pop()
                    try:
                        rsp = self._jls.process(value)
                        self.pubsub.publish(value['rsp_topic'], rsp)
                    except Exception:
                        _log.exception('During jls process')
                continue
            if cmd == 'request':
                key = (value['rsp_topic'], value['rsp_id'])
                requests.insert(key, value)
            elif cmd == 'close':
                do_quit = True
            else:
                _log.warning('unsupported command %s', cmd)

    def close(self):
        _log.info('close %s', self.path)
        jls, self._jls, thread, self._thread = self._jls, None, self._thread, None
        if thread is not None:
            self._queue.put(['close', None])
            thread.join()
        if jls is not None:
            jls.close()
        _log.info('close done %s', self.path)

    def on_action_close(self):
        self.close()
        self.pubsub.unregister(self, delete=True)

    def on_action_request(self, value):
        self._queue.put(['request', value])

    def on_action_annotations_request(self, value):
        base, ext = os.path.splitext(self.path)
        path = f'{base}.anno*{ext}'
        rsp_topic = value['rsp_topic']
        paths = glob.glob(path)
        if not len(paths):
            self.pubsub.publish(rsp_topic, None)
        else:
            annotations_load(paths, self.pubsub, rsp_topic)

    @staticmethod
    def on_cls_action_open(pubsub, topic, value):
        if isinstance(value, str):
            path = value
        else:
            raise ValueError(f'unsupported value {value}')
        m = re.match(r'(.+)\.anno[^\.]*\.jls', path)
        if bool(m):
            path = m.group(1) + '.jls'
        if not os.path.isfile(path):
            _log.warning('open %s not found (from %s)', path, value)
            return
        _log.info('open %s', path)
        obj = JlsSource(path)
        pubsub.register(obj)

    @staticmethod
    def on_cls_action_finalize(pubsub, topic, value):
        instances = pubsub.query(f'{get_topic_name(JlsSource)}/instances')
        for instance_unique_id in list(instances):
            instance = get_instance(instance_unique_id, default=None)
            if instance is not None:
                instance.close()
