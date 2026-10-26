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


"""Test the documentation URLs."""

import unittest
from joulescope_ui import urls


class TestUrls(unittest.TestCase):

    def test_docs_urls(self):
        names = [n for n in dir(urls) if n.endswith(('_USERS_GUIDE', '_PRODUCT'))]
        self.assertIn('JS320_USERS_GUIDE', names)
        for name in names:
            url = getattr(urls, name)
            with self.subTest(name=name):
                self.assertTrue(url.startswith(urls.DOCS), url)
                self.assertTrue(url.endswith('/'), url)

    def test_product_guides(self):
        for model in ['JS110', 'JS220', 'JS220PLUS', 'JS320']:
            product = getattr(urls, f'{model}_PRODUCT')
            self.assertEqual(product, f'{urls.DOCS}products/{model.lower()}/')
            self.assertEqual(getattr(urls, f'{model}_USERS_GUIDE'), product + 'guide/')
