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


import types
import weakref


class PubSubCallable:
    """Support callables for PubSub subcribe and unsubscribe.

    :param fn: The callable.  For methods, store a weakref to the instance.
    """

    def __init__(self, fn: callable, topic=None):
        self._auto_unsub = False
        self.topic = topic
        if isinstance(fn, types.MethodType):
            self._object_ref = weakref.ref(fn.__self__)
            self._fn = fn.__func__
        else:
            if hasattr(fn, '__func__'):  # static method support
                fn = fn.__func__
            self._object_ref = None
            self._fn = fn
        code = fn.__code__
        arg_count = code.co_argcount
        if arg_count and self._object_ref is not None:
            arg_count -= 1
        if not 0 <= arg_count <= 3:
            raise ValueError(f'invalid function {fn}')
        self._arg_count = arg_count

    def __call__(self, pubsub, topic: str, value):
        if self._object_ref is not None:
            obj = self._object_ref()
            if obj is None:
                if not self._auto_unsub:
                    self._auto_unsub = True
                    pubsub.unsubscribe(self)
                return
            if self._arg_count == 0:
                return self._fn(obj)
            elif self._arg_count == 1:
                return self._fn(obj, value)
            elif self._arg_count == 2:
                return self._fn(obj, topic, value)
            elif self._arg_count == 3:
                return self._fn(obj, pubsub, topic, value)
            else:
                raise RuntimeError('invalid')
        else:
            if self._arg_count == 0:
                return self._fn()
            elif self._arg_count == 1:
                return self._fn(value)
            elif self._arg_count == 2:
                return self._fn(topic, value)
            elif self._arg_count == 3:
                return self._fn(pubsub, topic, value)
            else:
                raise RuntimeError('invalid')

    def __eq__(self, other):
        self_obj = None if self._object_ref is None else self._object_ref()
        other_obj = None if other._object_ref is None else other._object_ref()
        return self_obj == other_obj and self._fn == other._fn
