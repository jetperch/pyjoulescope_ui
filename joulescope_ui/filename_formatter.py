# Copyright 2024 Jetperch LLC
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

from joulescope_ui import N_, time64, pubsub_singleton, get_topic_name
import os


_DEVICE_IDENTIFIER = N_('The device identifier.')
_DEVICE_NAME = N_('The user-configurable device name.')
_DEVICE_MODEL = N_('The device model.')
_DEVICE_SERIAL_NUMBER = N_('The device serial number.')
_FILENAME_CONFIG = N_('Configure the filename')
_REPLACEMENTS = N_('The filename supports the following replacements.')
_TIMESTAMP = N_('The current timestamp.')
_COUNT = N_('The number of times the filename has been used.')
_PROCESS_ID = N_('The process ID for this Joulescope UI invocation.')


HTML_STYLE = """\
<style>
table {
  border-collapse: collapse
}
th, td {
  padding: 5px;
  border: 1px solid;
}
</style>
"""


def filename_tooltip(device_id=None):
    device_id_str = f"""\
      <tr>
        <td>{{device_id}}</td>
        <td>{_DEVICE_IDENTIFIER}</td>
      </tr>
      <tr>
        <td>{{device_name}}</td>
        <td>{_DEVICE_NAME}</td>
      </tr>
      <tr>
        <td>{{device_model}}</td>
        <td>{_DEVICE_MODEL}</td>
      </tr>
      <tr>
        <td>{{device_serial_number}}</td>
        <td>{_DEVICE_SERIAL_NUMBER}</td>
      </tr>\
    """
    if not device_id:
        device_id_str = ''

    return f"""\
    <html><header>{HTML_STYLE}</header>
    <body>
    <h3>{_FILENAME_CONFIG}</h3>
    <p>{_REPLACEMENTS}
    <p><table>
      <tr>
        <td>{{timestamp}}</td>
        <td>{_TIMESTAMP}</td>
      </tr>
      <tr>
        <td>{{count}}</td>
        <td>{_COUNT}</td>
      </tr>
      {device_id_str}
      <tr>
        <td>{{process_id}}</td>
        <td>{_PROCESS_ID}</td>
      </tr>  
    </table></p></body></html>
    """


def filename_formatter(filename, count, device_id=None, **kwargs):
    """Format a filename.

    :param filename: The filename to format.
    :param count: The number of times the file type has been created.
    :param device_id: The optional device_id, when relevant.
    :return: The formatted filename.
    """
    kwargs['count'] = count
    if device_id is None:
        kwargs['device_id'] = ''
        kwargs['device_model'], kwargs['device_serial_number'] = '', ''
        kwargs['device_name'] = ''
    else:
        kwargs['device_id'] = device_id
        kwargs['device_model'], kwargs['device_serial_number'] = device_id.split('-')
        kwargs['device_name'] = pubsub_singleton.query(f'{get_topic_name(device_id)}/settings/name')
    kwargs.setdefault('timestamp', time64.filename(''))
    kwargs.setdefault('process_id', os.getpid())
    filename = filename.replace('{count}', '{count:04d}')
    filename = filename.replace('{process_id}', '{process_id:06d}')
    return filename.format(**kwargs)
