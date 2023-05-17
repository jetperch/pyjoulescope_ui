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

import threading
from pyjls import Reader, AnnotationType, SignalType
from joulescope_ui.jls_v2 import TO_UI_SIGNAL_NAME
import logging
import numpy as np


_CHUNK_SIZE = 1024


def _run(paths, pubsub, rsp_topic):
    _log = logging.getLogger(__name__)
    if isinstance(paths, str):
        paths = [paths]
    for path in paths:
        with Reader(path) as jls:
            for signal_id, signal in jls.signals.items():
                if signal.name not in TO_UI_SIGNAL_NAME:
                    if signal.name != 'global_annotation_signal':
                        _log.warning('unsupported signal name: %s', signal.name)
                    continue
                signal_name = TO_UI_SIGNAL_NAME[signal.name]
                dual_vmarkers = {}
                dual_hmarkers = {}

                # force UTC load
                if signal.signal_type == SignalType.FSR:
                    jls.sample_id_to_timestamp(signal_id, signal.sample_id_offset)

                annotations = []

                def _on_annotation(timestamp, y, annotation_type, group_id, data):
                    nonlocal annotations
                    # print(f'{timestamp}, {y}, {annotation_type}, {group_id}, {data}')
                    if signal.signal_type == SignalType.FSR:
                        timestamp = jls.sample_id_to_timestamp(signal_id, timestamp)
                    elif signal.signal_type == SignalType.VSR:
                        pass  # already in UTC seconds
                    else:
                        raise RuntimeError(f'invalid signal type {signal.signal_type}')

                    if annotation_type == AnnotationType.TEXT:
                        a = {
                            'annotation_type': 'text',
                            'plot_name': signal_name,
                            'text': data,
                            'text_show': True,
                            'shape': group_id,
                            'x': timestamp,
                            'y': y,
                            'y_mode': 'manual' if y is not None and np.isfinite(y) else 'centered'
                        }
                        annotations.append(a)
                    elif annotation_type == AnnotationType.VMARKER:
                        if data[-1] in 'ab':
                            name = data[:-1]
                            if name in dual_vmarkers:
                                a = dual_vmarkers.pop(name)
                                key = 'pos1' if (data[-1] == 'a') else 'pos1'
                                a[key] = timestamp
                                annotations.append(a)
                            else:
                                dual_vmarkers[name] = {
                                    'annotation_type': 'x',
                                    'dtype': 'dual',
                                    'pos1': timestamp,
                                    'pos2': timestamp,
                                    'changed': True,
                                    'text_pos1': 'right',
                                    'text_pos2': 'off',
                                }
                        else:
                            a = {
                                'annotation_type': 'x',
                                'dtype': 'single',
                                'pos1': timestamp,
                                'changed': True,
                                'text_pos1': 'right',
                            }
                            annotations.append(a)
                    elif annotation_type == AnnotationType.HMARKER:
                        if data[-1] in 'ab':
                            name = data[:-1]
                            if name in dual_hmarkers:
                                a = dual_hmarkers.pop(name)
                                key = 'pos1' if (data[-1] == 'a') else 'pos1'
                                a[key] = y
                                annotations.append(a)
                            else:
                                dual_hmarkers[name] = {
                                    'annotation_type': 'y',
                                    'plot_name': signal_name,
                                    'dtype': 'dual',
                                    'pos1': y,
                                    'pos2': y,
                                    'changed': True,
                                }
                        else:
                            a = {
                                'annotation_type': 'y',
                                'plot_name': signal_name,
                                'dtype': 'single',
                                'pos1': y,
                                'changed': True,
                            }
                            annotations.append(a)
                    else:
                        _log.warning('Unsupported annotation type %s', annotation_type)

                    if len(annotations) >= _CHUNK_SIZE:
                        pubsub.publish(rsp_topic, annotations)
                        annotations = []  # New list, cannot clear

                    return False

                jls.annotations(signal_id, 0, _on_annotation)
                if len(annotations):
                    pubsub.publish(rsp_topic, annotations)
                    annotations = []

    pubsub.publish(rsp_topic, None)  # done indication


def load(paths, pubsub, rsp_topic):
    kwargs = {
        'paths': paths,
        'pubsub': pubsub,
        'rsp_topic': rsp_topic,
    }
    thread = threading.Thread(target=_run, kwargs=kwargs)
    thread.start()
    return thread
