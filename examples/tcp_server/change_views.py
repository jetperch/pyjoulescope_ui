#!/usr/bin/env python3
"""Example: connect to the Joulescope UI TCP server and interact with it.

Usage:
    1. Start the UI with the server enabled:
           python -m joulescope_ui --tcp-server

    2. Run this script in a separate terminal:
           python examples/tcp_server/change_views.py
"""

import json
import os
import sys
import time

# Add the repo root to the path when running from the examples directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from joulescope_ui.tcp_client import Client


def find_credentials():
    """Load server credentials from the auto-generated server.json file."""
    # The UI writes server.json to the app path (common/settings/paths/app):
    #   Windows: %LOCALAPPDATA%/joulescope/
    #   macOS:   ~/Library/Application Support/joulescope/
    #   Linux:   ~/.joulescope/
    paths = [
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'joulescope', 'server.json'),
        os.path.expanduser('~/Library/Application Support/joulescope/server.json'),
        os.path.expanduser('~/.joulescope/server.json'),
    ]
    for p in paths:
        if os.path.isfile(p):
            with open(p) as f:
                return json.load(f)
    return None


def main():
    # Try to auto-discover credentials
    creds = find_credentials()
    if creds is None:
        print('Could not find server.json. Make sure the UI is running with --tcp-server.')
        print('You can also pass token and port manually.')
        return 1

    token = creds['token']
    port = creds['port']
    print(f'Connecting to localhost:{port}...')

    client = Client(port=port, token=token)
    client.open()
    print('Connected and authenticated.')

    # --- Query current active view ---
    active_view = client.query('registry/view/settings/active')
    print(f'Current active view: {active_view}')

    # --- Enumerate available views ---
    views = client.enumerate('registry/view/instances')
    print(f'Available view instances: {views}')

    # --- Switch to Multimeter view ---
    print('Switching to Multimeter view...')
    client.publish('registry/view/settings/active', 'view:multimeter')
    time.sleep(0.5)

    active_view = client.query('registry/view/settings/active')
    print(f'Active view is now: {active_view}')

    # --- Subscribe to statistics (if a device is connected) ---
    print('\nListening for statistics for 3 seconds...')
    stats_received = []

    def on_stats(topic, value):
        stats_received.append(value)
        print(f'  Stats: {topic}')

    client.subscribe('registry/+/events/statistics/!data', on_stats, ['pub'])
    time.sleep(3)

    if not stats_received:
        print('  (No statistics received - is a Joulescope connected?)')

    # --- Qt inspection ---
    print('\nInspecting widget tree (top-level only, max_depth=1)...')
    try:
        tree = client.qt_inspect(max_depth=1)
        print(f'  Root widget: {tree.get("class")} ({tree.get("objectName")})')
        for child in tree.get('children', []):
            print(f'    Child: {child.get("class")} ({child.get("objectName")})')
    except Exception as e:
        print(f'  Qt inspection error: {e}')

    # --- Switch to Oscilloscope view ---
    print('\nSwitching to Oscilloscope view...')
    client.publish('registry/view/settings/active', 'view:oscilloscope')
    time.sleep(0.5)
    active_view = client.query('registry/view/settings/active')
    print(f'Active view is now: {active_view}')

    client.close()
    print('\nDone.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
