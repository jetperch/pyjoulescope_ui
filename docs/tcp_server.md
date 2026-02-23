
# TCP Server

The TCP server extends the Joulescope UI's [PubSub](pubsub.md) system to
external processes over a TCP socket connection.  It enables two capabilities:

1. **Remote PubSub** -- Subscribe to topics, publish values, and query
   state from a separate process.
2. **Qt widget inspection** -- Traverse the widget tree, read/write
   properties, inject input events, and capture screenshots for
   test automation.

The server runs an asyncio event loop in a dedicated thread and does not
block the Qt event thread.  Streaming signal data (up to ~16 MB/s at
1 MHz) is sent as raw binary, avoiding JSON serialization overhead.


## Quick start

Start the UI with the TCP server enabled:

    python -m joulescope_ui --tcp-server

Connect from another Python process:

```python
import json
from joulescope_ui.tcp_client import Client

# Load auto-discovered credentials
#   Windows: %LOCALAPPDATA%/joulescope/server.json
#   macOS:   ~/Library/Application Support/joulescope/server.json
#   Linux:   ~/.joulescope/server.json
with open(server_json_path) as f:
    creds = json.load(f)

client = Client(port=creds['port'], token=creds['token'])
client.open()

# Switch to the Multimeter view
client.publish('registry/view/settings/active', 'view:multimeter')

# Query current view
print(client.query('registry/view/settings/active'))

client.close()
```

See `examples/tcp_server/change_views.py` for a complete working example
that auto-discovers the credentials file.


## Authentication

On startup the server generates a random token and writes it along with
the port number to `server.json` in the application data directory
(`common/settings/paths/app`).  The client must send this token as the
first message after connecting.  The file is deleted when the UI exits.


## Client API

The client is provided by `joulescope_ui.tcp_client.Client`.  It runs an
internal receive thread so subscription callbacks fire asynchronously.

### Connection

```python
client = Client(host='127.0.0.1', port=21861, token='...')
client.open()
# ... use the client ...
client.close()
```

`Client` also supports the context manager protocol:

```python
with Client(port=port, token=token) as client:
    client.publish(...)
```

### PubSub operations

| Method | Description |
|--------|-------------|
| `subscribe(topic, callback, flags=None)` | Subscribe to a topic. `callback(topic, value)` is called for each publish. |
| `unsubscribe(topic, callback=None)` | Unsubscribe from a topic. |
| `publish(topic, value)` | Publish a JSON-serializable value. |
| `query(topic)` | Query the retained value of a topic. |
| `enumerate(topic, absolute=None)` | List child topics. |

### Qt inspection

| Method | Description |
|--------|-------------|
| `qt_inspect(path='', max_depth=50)` | Return the widget tree as a nested dict. |
| `qt_action(action, path='', **kwargs)` | Perform a UI action (see below). |
| `qt_screenshot(path='')` | Capture a widget as PNG bytes. |

#### Widget paths

Widgets are addressed by a forward-slash-separated path of `objectName`
values.  When no `objectName` matches, `ClassName:index` syntax selects
by class name and 0-based index among siblings.  An empty path selects the
root window.

Examples:

    central_widget
    central_widget/dock_manager
    central_widget/QWidget:0

#### Actions

**Click:**

```python
client.qt_action('click', path='my_button')
client.qt_action('click', path='my_button', pos=[10, 10], button='LeftButton')
```

**Key press:**

```python
client.qt_action('key', path='my_input', key='A', text='a')
client.qt_action('key', path='my_input', key='Return')
```

**Property read/write:**

```python
result = client.qt_action('get_property', path='my_widget', property='visible')
client.qt_action('set_property', path='my_widget', property='enabled', value=False)
```

**Screenshot:**

```python
png_bytes = client.qt_screenshot('central_widget')
with open('screenshot.png', 'wb') as f:
    f.write(png_bytes)
```


## Common PubSub topics

| Topic | Type | Description |
|-------|------|-------------|
| `registry/view/settings/active` | str | Active view: `'view:multimeter'`, `'view:oscilloscope'`, `'view:file'` |
| `registry/view/actions/!widget_open` | obj | Open a widget by class name or dict |
| `registry/view/actions/!widget_close` | obj | Close a widget instance |
| `registry/+/events/statistics/!data` | obj | Periodic statistics from connected devices |
| `registry/+/events/signals/{signal}/!data` | obj | Full-rate signal data (numpy arrays) |

Use `client.enumerate('registry')` to discover the full topic tree at
runtime.


## Wire protocol

The protocol uses length-prefixed binary frames:

    [4B total_length][1B version][1B msg_type][2B header_length][header_json][binary_payload]

- `total_length` -- uint32 big-endian, length of everything after this field.
- `version` -- protocol version (currently 1).
- `msg_type` -- message type identifier.
- `header_length` -- uint16 big-endian, length of the JSON header.
- `header_json` -- UTF-8 JSON-encoded header dict.
- `binary_payload` -- optional raw bytes (e.g. numpy array data).

Control messages carry only a JSON header.  Streaming data messages
(`publish_data`, 0x04) carry a JSON header with metadata (dtype, shape,
sample_id, etc.) followed by raw `ndarray.tobytes()` data.  The receiver
reconstructs the array with `numpy.frombuffer(payload, dtype).reshape(shape)`.

### Message types

| ID | Name | Direction |
|----|------|-----------|
| 0x00 | auth | client -> server |
| 0x01 | subscribe | client -> server |
| 0x02 | unsubscribe | client -> server |
| 0x03 | publish | bidirectional |
| 0x04 | publish_data | server -> client |
| 0x05 | query | client -> server |
| 0x06 | query_response | server -> client |
| 0x07 | enumerate | client -> server |
| 0x08 | enumerate_response | server -> client |
| 0x10 | qt_inspect | client -> server |
| 0x11 | qt_inspect_response | server -> client |
| 0x12 | qt_action | client -> server |
| 0x13 | qt_screenshot | client -> server |
| 0x14 | qt_screenshot_response | server -> client |
| 0xFD | auth_ok | server -> client |
| 0xFE | error | server -> client |
| 0xFF | close | bidirectional |


## Architecture

```
  External Client (TCP)
        |
        v
  +---------------------+
  |  asyncio event loop  |  <-- dedicated Python thread
  |  (TCP server)        |
  +------+------^--------+
         |      |
  publish |      | call_soon_threadsafe(forward)
  to queue|      |
         v      |
  +---------------------+
  |  PubSub singleton   |  <-- processes on Qt main thread
  +------+--------------+
         |
         v
  +---------------------+
  |  Qt widgets / UI    |
  +---------------------+
```

**Inbound (client to app):** The asyncio thread receives frames,
deserializes them, and calls `pubsub.publish(topic, value)`.  PubSub's
existing thread-safe `_send` queue and `notify_fn` handle cross-thread
delivery to the Qt main thread.

**Outbound (app to client):** A PubSub subscriber callback on the Qt
thread serializes the message to bytes and calls
`loop.call_soon_threadsafe()` to schedule the socket write on the asyncio
thread.

**Qt inspection:** Requests are routed through a PubSub action topic so
the actual Qt operations execute on the main thread.  Results are passed
back to the asyncio thread via `concurrent.futures.Future`.

### Backpressure

Per-client write buffers are monitored.  If a client's buffer exceeds
32 MB, streaming data frames are dropped (the client can detect gaps via
`sample_id` discontinuities).  Control and settings messages are always
delivered.


## Module structure

```
joulescope_ui/
    tcp_server/
        __init__.py       # TcpServer class (asyncio loop + thread lifecycle)
        protocol.py       # Frame encoding/decoding, message type constants
        bridge.py         # PubSub <-> network bridge
        qt_inspector.py   # Widget traversal, screenshots, synthetic events
        test/
            test_protocol.py
            test_integration.py
    tcp_client.py         # Python client library
```
