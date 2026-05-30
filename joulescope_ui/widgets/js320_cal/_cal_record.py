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

"""Read-only parser for the JS320 calibration record (slot-table display).

The cal manager owns all writes, signing, and hashing.  This module only
extracts the human-readable header fields used to populate the slot
table in the UI and to surface "driver-generated" provenance.

Layout reference: ``joulescope_driver/doc/js320_cal.md`` (table under
"Calibration record layout").
"""

import struct


JS320_CALIBRATION_SIZE = 1024
JS320_CALIBRATION_HEADER = b'JS320cal\x0D\x0A \x0A\x1A\xB2\x1C\x00'  # 16 bytes
JSDRV_SIGNATURE_MAGIC = b'JSDRV_OFFSET_CAL'  # 16 bytes


def parse_record(data):
    """Return slot metadata or None if the record is invalid."""
    if data is None or len(data) < JS320_CALIBRATION_SIZE:
        return None
    if bytes(data[:16]) != JS320_CALIBRATION_HEADER:
        return None
    serial = bytes(data[24:32]).split(b'\x00', 1)[0].decode('utf-8', errors='replace')
    info = bytes(data[40:72]).split(b'\x00', 1)[0].decode('utf-8', errors='replace')
    create_time = struct.unpack_from('<q', data, 32)[0]
    cal_source_version = struct.unpack_from('<I', data, 72)[0]
    sig_magic = bytes(data[952:968])
    is_driver_generated = sig_magic == JSDRV_SIGNATURE_MAGIC
    driver_version_u32 = struct.unpack_from('<I', data, 968)[0]
    return {
        'serial_number': serial,
        'source_info': info,
        'create_time': create_time,
        'cal_source_version': cal_source_version,
        'is_driver_generated': is_driver_generated,
        'driver_version_u32': driver_version_u32,
    }
