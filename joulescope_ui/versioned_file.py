# Copyright 2023 Jetperch LLC
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


"""Automatically save versioned files with option to restore."""


import builtins
import glob
import os
import shutil


_VERSION_COUNT = 10  # default number of versions to maintain


class VersionedFile:
    """Versioned file wrapper that wraps a file instance.

    :param path: The path to the "normal" filename.
    :param version_count: The number of file versions to support.
        None (default) is equivalent to _VERSION_COUNT.
    """

    def __init__(self, path, version_count=None):
        self._path = path
        self._tmp_path = version_path(path, f'tmp_{os.getpid()}')
        self._mode = None
        self._version_count = version_count
        self._fh = None

    def __getattr__(self, item):
        return getattr(self._fh, item)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def open(self, mode=None, **kwargs):
        if mode is None:
            mode = 'r'
        self._mode = mode
        if 'a' in mode:
            shutil.copy(self._path, self._tmp_path)
            path = self._tmp_path
        elif self.is_write:
            if os.path.exists(self._tmp_path):
                os.remove(self._tmp_path)  # should not be there, remove to recover
            path = self._tmp_path
        else:
            path = self._path
        self._fh = builtins.open(path, mode=mode, **kwargs)
        return self

    @property
    def is_write(self):
        return 'w' in self._mode or 'x' in self._mode or 'a' in self._mode

    def close(self):
        fh, self._fh = self._fh, None
        fh.close()
        if self.is_write:
            glob_path = version_path(self._path, '*')
            n_max = -1
            for p in glob.glob(glob_path):
                n_str = p.split('.')[-2]
                try:
                    n_max = max(int(n_str), n_max)
                except ValueError:
                    pass
            for n in range(n_max + 1, -1, -1):
                path = version_path(self._path, n)
                if n <= 0:
                    path_next = self._path
                else:
                    path_next = version_path(self._path, n - 1)
                if os.path.isfile(path):
                    os.remove(path)
                if n < self._version_count and os.path.isfile(path_next):
                    os.rename(path_next, path)
            os.replace(self._tmp_path, self._path)


def version_path(path: str, n):
    """The path to the versioned file.

    :param path: The base path to the file.  This path
        must not contain any versioning information that
        is added by this function.
    :param n: The version number.  Alternatively, this
        may be a string to support temporary files
        and globs.
    """
    if n is None:
        return path
    dirname = os.path.dirname(path)
    basename = os.path.basename(path)
    parts = basename.split('.')
    if isinstance(n, int):
        n = f'{n:03}'
    elif not isinstance(n, str):
        raise ValueError(f'Invalid value for n: {n}')
    basename = '.'.join(parts[:-1] + [n, parts[-1]])
    return os.path.join(dirname, basename)


def open(path: str, mode=None, version_count=None, **kwargs):
    """Open a versioned file.

    :param path: The path to the versioned file.  This path
        must not contain any versioning information that
        is added by this module.
    :param mode: The file open mode string.
    :param version_count: The number of versions to keep.
        None (default) is equivalent to _VERSION_COUNT.
    :param kwargs: Additional arguments for :func:`builtins.open`.
    """
    version_count = _VERSION_COUNT if version_count is None else int(version_count)
    fh = VersionedFile(path, version_count)
    return fh.open(mode, **kwargs)


def revert(path: str, count=None):
    """Revert to a previously saved version.

    :param path: The path to the versioned file.  This path
        must not contain any versioning information that
        is added by this module.
    :param count: The number of versions to revert.
        None is equivalent to 1.
    """
    if count is None:
        count = 1
    else:
        count = int(count)
        if count < 1:
            raise ValueError(f'invalid count {count}')
    if os.path.isfile(path):
        os.remove(path)
    path_last = path
    n = count - 1
    while True:
        p = version_path(path, n)
        if not os.path.isfile(p):
            break
        os.rename(p, path_last)
        path_last = p
        n += 1


def remove(path: str):
    """Remove the versioned file and all versions.

    :param path: The path to the versioned file.  This path
    must not contain any versioning information that
    is added by this module.
    """
    if os.path.isfile(path):
        os.remove(path)
    n = 0
    while True:
        p = version_path(path, n)
        if os.path.isfile(p):
            os.remove(p)
        else:
            break
        n += 1
