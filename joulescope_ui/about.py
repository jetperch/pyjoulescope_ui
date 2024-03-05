# Copyright 2018-2024 Jetperch LLC
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


from joulescope_ui import __version__ as ui_version
from joulescope_ui import N_
from pyjoulescope_driver import __version__ as jsdrv_version
from pyjls import __version__ as jls_version
import platform
import sys


_TITLE = N_('About the Joulescope UI')
_VERSIONS = N_('Version Information')


ABOUT = f"""\
<html><head>
<title>{_TITLE}</title>
{{style}}
</head>
<body>
<p><a href="https://www.joulescope.com">https://www.joulescope.com</a></p>
<p>{_VERSIONS}:</p>
<table>
<tr><td>UI</td><td>{ui_version}</td></tr>
<tr><td>driver</td><td>{jsdrv_version}</td></tr> 
<tr><td>JLS</td><td>{jls_version}</td></tr>
<tr><td>Python</td><td>{sys.version}</td></tr>
<tr><td>Platform</td><td>{platform.platform()}</td></tr>
<tr><td>Processor</td><td>{platform.processor()}</td></tr>
</table>

<pre>
Copyright 2018-2024 Jetperch LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
</pre>
</body>
</html>
"""
