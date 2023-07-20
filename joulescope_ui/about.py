# Copyright 2018-2023 Jetperch LLC
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
from pyjoulescope_driver import __version__ as jsdrv_version
from pyjls import __version__ as jls_version
import platform
import sys


_HEADER = """\
<html>
<head>
<title>About the Joulescope UI</title>
{style}
</head>
"""


_FOOTER = '</html>'


_ABOUT = """\
<body>
Joulescope UI version {ui_version}<br/> 
Joulescope driver version {jsdrv_version}<br/>
JLS version {jls_version}<br/>
Python {sys_version}<br/>
Platform {platform}<br/>
Processor {processor}<br/>
<a href="https://www.joulescope.com">https://www.joulescope.com</a>

<pre>
Copyright 2018-2023 Jetperch LLC

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
"""


def load():
    txt = _ABOUT.format(
        ui_version=ui_version,
        jsdrv_version=jsdrv_version,
        jls_version=jls_version,
        sys_version=sys.version,
        platform=platform.platform(),
        processor=platform.processor(),
    )
    return _HEADER + txt + _FOOTER
