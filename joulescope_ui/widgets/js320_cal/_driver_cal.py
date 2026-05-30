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

"""JS320 calibration via the per-device cal handler.

Local mirror of the reference wrapper in
``joulescope_driver/doc/js320_cal.md``.  Replace with an import from
``pyjoulescope_driver`` once it ships its own ``cal_js320`` module.

The cal handler is a per-device subsystem that operates on the existing
open device; the caller is responsible for keeping the device open
(``jsdrv_open(... RESUME)``) for the duration of the operation. Topics
are device-prefixed: every publish/subscribe goes to ``<device>/h/cal/``.
"""

import itertools
import json
import logging
import struct
import threading
import time


_log = logging.getLogger(__name__)

OP_SLOT_READ = 0
OP_SLOT_COPY = 1
OP_CURRENT_OFFSET = 2
OP_VOLTAGE_OFFSET = 3

SLOT_ACTIVE = 0
SLOT_TRIM2 = 1
SLOT_TRIM1 = 2
SLOT_FIELD = 3
SLOT_LAB = 4
SLOT_FACTORY = 5

SLOT_NAMES = {
    SLOT_ACTIVE:  'ACTIVE',
    SLOT_TRIM2:   'TRIM2',
    SLOT_TRIM1:   'TRIM1',
    SLOT_FIELD:   'FIELD',
    SLOT_LAB:     'LAB',
    SLOT_FACTORY: 'FACTORY',
}
SLOT_IDS = {v: k for k, v in SLOT_NAMES.items()}

CAL_RECORD_SIZE = 1024
CAL_SIGNATURE_MAGIC = b'JSDRV_OFFSET_CAL'

# jsdrv_cal_cmd_s: u32 txn_id, u8 op, u8 src, u8 dst, u8 flags, u32 samples
_CMD = struct.Struct('<IBBBBI')
# jsdrv_cal_rsp_s: u32 txn_id, i32 status
_RSP = struct.Struct('<Ii')

_TXN_COUNTER = itertools.count(1)


def _next_txn_id():
    return next(_TXN_COUNTER) & 0xFFFFFFFF


def _run_op(driver, device_path, op, src_slot=0, dst_slot=0,
            samples_per_point=0, progress=None, timeout=60.0,
            collect_data=False, abort_event=None):
    """Publish ``<device>/h/cal/!cmd`` and wait for ``!rsp``.

    Returns the 1024-byte record on ``slot_read`` (when ``collect_data``)
    or ``None`` otherwise. Raises ``RuntimeError('aborted')`` if
    ``abort_event`` is set, ``TimeoutError`` on timeout, or
    ``RuntimeError`` with the last status message on driver-reported
    failure.
    """
    if progress is None:
        progress = lambda x, y: None

    txn_id = _next_txn_id()
    payload = _CMD.pack(txn_id, int(op), int(src_slot), int(dst_slot), 0,
                        int(samples_per_point))

    done = threading.Event()
    state = {'status': None, 'last_status': ''}
    data_buf = {'bytes': None}

    cmd_topic = f'{device_path}/h/cal/!cmd'
    rsp_topic = f'{device_path}/h/cal/!rsp'
    status_topic = f'{device_path}/h/cal/!status'
    data_topic = f'{device_path}/h/cal/!data'

    def on_status(topic, value):
        if not isinstance(value, str):
            return
        state['last_status'] = value
        try:
            entry = json.loads(value)
        except (ValueError, TypeError):
            return
        try:
            pct = float(entry.get('pct', 0.0))
        except (TypeError, ValueError):
            pct = 0.0
        progress(pct / 100.0,
                 f"{entry.get('state', '?')}: {entry.get('msg', '')}")

    def on_data(topic, value):
        if collect_data and isinstance(value, (bytes, bytearray, memoryview)):
            data_buf['bytes'] = bytes(value)

    def on_rsp(topic, value):
        if isinstance(value, (bytes, bytearray, memoryview)) and len(value) >= 8:
            rsp_txn, status = _RSP.unpack_from(bytes(value), 0)
            if rsp_txn != txn_id:
                return  # response for a different transaction
            state['status'] = int(status)
        else:
            state['status'] = -1
        done.set()

    progress(0.0, 'Starting JS320 calibration')
    driver.subscribe(status_topic, 'pub', on_status)
    driver.subscribe(data_topic, 'pub', on_data)
    driver.subscribe(rsp_topic, 'pub', on_rsp)
    try:
        # Fire-and-forget: the handler does not reply on h/cal/!cmd#,
        # so a nonzero publish timeout would always block to its
        # expiry. The outcome arrives on the !rsp subscription.
        driver.publish(cmd_topic, payload, timeout=0)
        deadline = None if timeout is None else (time.monotonic() + timeout)
        while not done.is_set():
            if abort_event is not None and abort_event.is_set():
                raise RuntimeError('aborted')
            remaining = 0.25
            if deadline is not None:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError(
                        f'JS320 cal timed out after {timeout:.0f}s '
                        f'(last status: {state["last_status"]})')
                remaining = min(remaining, left)
            done.wait(remaining)
    finally:
        driver.unsubscribe(status_topic, on_status)
        driver.unsubscribe(data_topic, on_data)
        driver.unsubscribe(rsp_topic, on_rsp)

    if state['status']:
        raise RuntimeError(
            f'JS320 cal failed: status={state["status"]} '
            f'(last status: {state["last_status"]})')
    progress(1.0, 'Complete')
    return data_buf['bytes']


def slot_read(driver, device_path, slot, **kwargs):
    if isinstance(slot, str):
        slot = SLOT_IDS[slot.upper()]
    data = _run_op(driver, device_path, OP_SLOT_READ,
                   src_slot=slot, collect_data=True, **kwargs)
    if data is None or len(data) != CAL_RECORD_SIZE:
        raise RuntimeError(
            f'slot_read returned {len(data) if data else 0} bytes')
    return data


def slot_copy(driver, device_path, src_slot, dst_slot, **kwargs):
    if isinstance(src_slot, str):
        src_slot = SLOT_IDS[src_slot.upper()]
    if isinstance(dst_slot, str):
        dst_slot = SLOT_IDS[dst_slot.upper()]
    _run_op(driver, device_path, OP_SLOT_COPY,
            src_slot=src_slot, dst_slot=dst_slot, **kwargs)


def current_offset_cal(driver, device_path, samples_per_point=0, **kwargs):
    # ~50 s with default 200k samples; ~12 s with 5000 samples on HIL.
    kwargs.setdefault('timeout', 90.0)
    _run_op(driver, device_path, OP_CURRENT_OFFSET,
            samples_per_point=samples_per_point, **kwargs)


def voltage_offset_cal(driver, device_path, samples_per_point=0, **kwargs):
    # ~5 s with default 200k samples; ~3 s with 5000 samples on HIL.
    kwargs.setdefault('timeout', 30.0)
    _run_op(driver, device_path, OP_VOLTAGE_OFFSET,
            samples_per_point=samples_per_point, **kwargs)
