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
        <td>{N_('The device identifier.')}</td>
      </tr>
      <tr>
        <td>{{device_name}}</td>
        <td>{N_('The user-configurable device name.')}</td>
      </tr>
      <tr>
        <td>{{device_model}}</td>
        <td>{N_('The device model.')}</td>
      </tr>
      <tr>
        <td>{{device_serial_number}}</td>
        <td>{N_('The device serial number.')}</td>
      </tr>\
    """
    if not device_id:
        device_id_str = ''

    return f"""\
    <html><header>{HTML_STYLE}</header>
    <body>
    <h3>{N_('Configure the filename')}</h3>
    <p>{N_('The filename supports the following replacements.')}
    <p><table>
      <tr>
        <td>{{timestamp}}</td>
        <td>{N_('The current timestamp.')}</td>
      </tr>
      <tr>
        <td>{{count}}</td>
        <td>{N_('The number of times the filename has been used.')}</td>
      </tr>
      {device_id_str}
      <tr>
        <td>{{process_id}}</td>
        <td>{N_('The process ID for this Joulescope UI invocation.')}</td>
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
