# Copyright 2025 Jetperch LLC
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

import logging
import subprocess


_log = logging.getLogger(__name__)

# https://learn.microsoft.com/en-us/windows-server/networking/windows-time-service/configuring-systems-for-high-accuracy
# https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/reg-add
# https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_powershell_exe


W32TIME_HIGH_ACCURACY = r"""
    sc.exe config W32Time start= auto
    sc.exe start W32Time
    reg add HKLM\SYSTEM\CurrentControlSet\Services\W32Time\Config /v MinPollInterval /t REG_DWORD /d 6 /f 
    reg add HKLM\SYSTEM\CurrentControlSet\Services\W32Time\Config /v MaxPollInterval /t REG_DWORD /d 6 /f 
    reg add HKLM\SYSTEM\CurrentControlSet\Services\W32Time\Config /v UpdateInterval /t REG_DWORD /d 100 /f 
    reg add HKLM\SYSTEM\CurrentControlSet\Services\W32Time\Config /v FrequencyCorrectRate /t REG_DWORD /d 2 /f 
    reg add HKLM\SYSTEM\CurrentControlSet\Services\W32Time\TimeProviders\NtpClient /v SpecialPollInterval /t REG_DWORD /d 64 /f 
    w32tm /config /update
    net stop w32time
    net start w32time
"""


def run_powershell_script_as_admin(script):
    """Run a PowerShell script with elevated admin privileges.

    :param script: The PowerShell script to run as text (not path).

    Some Windows 11 configurations disable PowerShell scripts.  We run our
    PowerShell script as inline text to avoid this.
    """
    _log.info(f'Run PowerShell script as admin:\n{script}')
    command = '; '.join(line.strip() for line in script.splitlines())
    try:
        process = subprocess.run(
            ["powershell.exe", "Start-Process", "powershell.exe",
             '-ArgumentList',
             f"'-NoProfile -ExecutionPolicy Bypass -Command \"{command}\"'",
             "-Verb", "runAs"],
            capture_output=True,
            check=True,
            shell=True,
        )
        _log.info(f'PowerShell script executed successfully:\n{process.stdout.decode(errors="ignore")}')
    except subprocess.CalledProcessError as e:
        _log.warning(f'PowerShell script execution failed:\n{e.stderr.decode(errors="ignore")}')


def run_w32time_high_accuracy():
    run_powershell_script_as_admin(W32TIME_HIGH_ACCURACY)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    run_w32time_high_accuracy()
