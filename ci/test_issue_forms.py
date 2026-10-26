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

"""Tests for ci/issue_forms.py.

Run from the repository root:
    pytest ci/test_issue_forms.py
"""

import os
import re
import sys
import yaml

_CI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _CI)

import issue_forms  # noqa: E402


def test_render_expands_shared_fields():
    forms = issue_forms.render('9.8.7')
    assert sorted(forms) == ['bug_form.yml', 'enhancement_form.yml', 'question_form.yml']
    for contents in forms.values():
        assert contents.startswith(issue_forms.HEADER)
        assert not re.search(r'[&*][A-Za-z_]', contents)  # no YAML anchors
        form = yaml.safe_load(contents)
        fields = {x.get('id'): x for x in form['body']}
        assert fields['version']['attributes']['options'] == ['9.8.7', 'other']
        assert 'JS320' in fields['Joulescope-model']['attributes']['options']
        assert 'Windows 11' in fields['Environment']['attributes']['options']


def test_render_keeps_form_specific_fields():
    forms = {k: yaml.safe_load(v) for k, v in issue_forms.render('1.0.0').items()}
    bug = {x.get('id'): x for x in forms['bug_form.yml']['body']}
    assert bug['Environment']['validations']['required'] is True
    assert bug['how-reproduce']['attributes']['value'] == '1. ...\n2. ...\n3. ...\n'
    enh = {x.get('id'): x for x in forms['enhancement_form.yml']['body']}
    assert 'validations' not in enh['Environment']
    assert forms['question_form.yml']['labels'] == ['question', 'triage']


def test_committed_forms_are_current():
    stale = issue_forms.generate(check=True)
    assert not stale, f'Run "python version_update.py" to regenerate: {stale}'
