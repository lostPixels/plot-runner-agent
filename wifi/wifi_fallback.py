#!/usr/bin/env python3
"""
Plot Runner WiFi fallback hotspot.

When wlan0 can't join any saved WiFi network for `fallback_delay` seconds (and
there's no wired link), bring up a WPA2 hotspot named "<hostname>-direct" from
the NetworkManager profile "plot-runner-hotspot". While the hotspot is up, try
the saved networks again every `retry_interval` seconds, but only when nobody
is using the hotspot.

Rules that keep the Pi reachable:
- Anything that takes wlan0 down ends with WiFi connected or the hotspot up.
- Saved networks are only removed by "Forget" on the page. Joining a network
  adds a new profile; a failed join deletes only that new profile.
- The fallback can't be turned off from the page, and timings are clamped.
- A file named force-hotspot on the boot partition keeps the hotspot up.
- The WiFi radio is unblocked, and NetworkManager restarted if it stops answering.

Standard library only, installed outside the app directory, so it keeps
working when the plotter API or its virtualenv is broken.
"""

import json
import logging
import os
import queue
import re
import socket
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

IFACE = os.environ.get('WIFI_IFACE', 'wlan0')
HOTSPOT_CON = os.environ.get('HOTSPOT_CONNECTION', 'plot-runner-hotspot')
HOTSPOT_ADDRESS = '10.42.0.1'
HOTSPOT_SUBNET = '10.42.0.'
UI_HOST = os.environ.get('WIFI_UI_HOST', '0.0.0.0')
UI_PORT = int(os.environ.get('WIFI_UI_PORT', '8080'))
STATE_DIR = Path(os.environ.get('STATE_DIRECTORY', '/var/lib/plot-runner-wifi'))
SETTINGS_FILE = STATE_DIR / 'settings.json'
PAGE = Path(__file__).resolve().parent / 'index.html'
FORCE_FILES = [Path(d) / n for d in ('/boot/firmware', '/boot')
               for n in ('force-hotspot', 'force-hotspot.txt')]

DEFAULTS = {'fallback_delay': 90, 'retry_interval': 300, 'manual_hold': 30}
LIMITS = {'fallback_delay': (30, 900), 'retry_interval': (120, 3600), 'manual_hold': (5, 240)}

TICK = 5                # seconds between checks
CONNECT_TIMEOUT = 45    # seconds NetworkManager gets to join a network
HOTSPOT_RETRY = 30      # seconds between tries when the hotspot won't start
UI_ACTIVE_WINDOW = 300  # a hotspot client used the page this recently: keep the hotspot up
IN_USE_RECHECK = 60     # hotspot in use at retry time: look again this much later
PROFILE_REFRESH = 60
SCAN_REFRESH = 60
NM_RESTART_AFTER = 120  # nmcli failing this long: restart NetworkManager
NM_RESTART_EVERY = 600

log = logging.getLogger('plot-runner-wifi')


# --- nmcli helpers ---------------------------------------------------------

def run(args, timeout=60):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, (p.stderr or p.stdout).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, '', str(e)


def nmcli(*args, timeout=60):
    return run(['nmcli', *args], timeout=timeout)


def split_terse(line):
    """Split a line of `nmcli -t -e yes` output on unescaped colons."""
    fields, cur, escaped = [], [], False
    for ch in line:
        if escaped:
            cur.append(ch)
            escaped = False
        elif ch == '\\':
            escaped = True
        elif ch == ':':
            fields.append(''.join(cur))
            cur = []
        else:
            cur.append(ch)
    fields.append(''.join(cur))
    return fields


def terse_rows(*args, width):
    rc, out, err = nmcli('-t', '-e', 'yes', *args)
    rows = [f for f in (split_terse(line) for line in out.splitlines()) if len(f) >= width]
    return rc, rows, err


def profile_fields(selector, ident, fields):
    """Read fields of one connection profile: {'802-11-wireless.ssid': 'x', ...}."""
    rc, out, _ = nmcli('-t', '-e', 'yes', '-f', fields, 'connection', 'show', selector, ident)
    if rc:
        return None
    values = {}
    for line in out.splitlines():
        parts = split_terse(line)
        if len(parts) >= 2:
            values[parts[0]] = ':'.join(parts[1:])
    return values


def hotspot_ssid():
    return socket.gethostname().split('.')[0][:25] + '-direct'


def nmcli_error(err):
    lines = (err or '').strip().splitlines()
    msg = re.sub(r'^Error:\s*', '', lines[-1]) if lines else ''
    return msg[:200] or 'unknown error'


# --- settings --------------------------------------------------------------

def clamp_settings(values):
    out = {}
    for key, (lo, hi) in LIMITS.items():
        if key in values:
            out[key] = max(lo, min(hi, int(values[key])))
    return out


def load_settings():
    settings = dict(DEFAULTS)
    try:
        settings.update(clamp_settings(json.loads(SETTINGS_FILE.read_text())))
    except (OSError, ValueError, TypeError, AttributeError):
        pass  # missing or bad file: defaults
    return settings


def save_settings(settings):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(settings, indent=2))
    os.replace(tmp, SETTINGS_FILE)


# --- watchdog --------------------------------------------------------------

class Watchdog:
    def __init__(self):
        self.settings = load_settings()
        self.actions = queue.Queue()
        self.events = deque(maxlen=80)
        self.busy = None
        self.last_attempt = None

        now = time.monotonic()
        self.offline_since = now      # boot counts as offline until WiFi shows up
        self.last_probe = now
        self.hotspot_retry_at = 0
        self.hold_until = 0
        self.last_ui_hit = 0
        self.nm_fail_since = None
        self.nm_restarted_at = 0
        self.radio_checked_at = 0
        self.forced_logged = False

        self.mode = 'starting'
        self.active_uuid = None
        self.wired = False
        self.wifi_ip = None
        self.clients = None
        self.profiles = []
        self.profiles_at = 0
        self.scan = []
        self.scan_at = None
        self.view = {}

    # -- bookkeeping

    def event(self, msg):
        log.info(msg)
        self.events.appendleft({'at': datetime.now().strftime('%b %d %H:%M:%S'), 'msg': msg})

    def note_ui_hit(self, ip):
        if ip and ip.startswith(HOTSPOT_SUBNET):
            self.last_ui_hit = time.monotonic()

    # -- observation

    def refresh_profiles(self, force=False):
        if not force and time.monotonic() - self.profiles_at < PROFILE_REFRESH:
            return
        rc, rows, _ = terse_rows('-f', 'NAME,UUID,TYPE,AUTOCONNECT,AUTOCONNECT-PRIORITY',
                                 'connection', 'show', width=5)
        if rc:
            return
        profiles = []
        for name, uuid, ctype, autoconnect, priority in (r[:5] for r in rows):
            if ctype != '802-11-wireless':
                continue
            f = profile_fields('uuid', uuid, '802-11-wireless.mode,802-11-wireless.ssid,802-11-wireless.hidden') or {}
            try:
                prio = int(priority)
            except ValueError:
                prio = 0
            profiles.append({
                'uuid': uuid, 'name': name,
                'ssid': f.get('802-11-wireless.ssid', ''),
                'mode': f.get('802-11-wireless.mode') or 'infrastructure',
                'hidden': f.get('802-11-wireless.hidden') == 'yes',
                'autoconnect': autoconnect == 'yes',
                'priority': prio,
            })
        self.profiles = profiles
        self.profiles_at = time.monotonic()

    def saved_networks(self):
        return [p for p in self.profiles if p['mode'] == 'infrastructure' and p['name'] != HOTSPOT_CON]

    def profile(self, uuid):
        return next((p for p in self.profiles if p['uuid'] == uuid), None)

    def refresh_scan(self, rescan=False):
        for attempt in range(3):
            rc, rows, _ = terse_rows('-f', 'IN-USE,SSID,SIGNAL,SECURITY', 'device', 'wifi', 'list',
                                     'ifname', IFACE, '--rescan', 'yes' if rescan else 'no', width=4)
            if rc == 0:
                break
            time.sleep(2)  # "scanning not allowed" right after a state change
        else:
            return
        best = {}
        for in_use, ssid, signal, security in (r[:4] for r in rows):
            if not ssid:
                continue
            try:
                sig = int(signal)
            except ValueError:
                sig = 0
            sec = '' if security in ('', '--') else security
            if ssid not in best or sig > best[ssid]['signal']:
                best[ssid] = {'ssid': ssid, 'signal': sig, 'security': sec, 'in_use': in_use == '*'}
            elif in_use == '*':
                best[ssid]['in_use'] = True
        self.scan = sorted(best.values(), key=lambda n: -n['signal'])
        self.scan_at = time.monotonic()

    def count_clients(self):
        rc, out, _ = run(['iw', 'dev', IFACE, 'station', 'dump'], timeout=10)
        return out.count('Station ') if rc == 0 else None

    def observe(self):
        """Update mode/wired/active_uuid. Returns False when NetworkManager isn't answering."""
        rc, devs, _ = terse_rows('-f', 'DEVICE,TYPE,STATE', 'device', 'status', width=3)
        if rc:
            return False
        _, active, _ = terse_rows('-f', 'UUID,DEVICE', 'connection', 'show', '--active', width=2)
        wlan = next((d for d in devs if d[0] == IFACE), None)
        self.wired = any(d[1] == 'ethernet' and d[2].startswith('connected') for d in devs)
        self.active_uuid = next((a[0] for a in active if a[1] == IFACE), None)

        if wlan is None:
            mode = 'missing'
        elif wlan[2].startswith('connected'):
            prof = self.profile(self.active_uuid)
            if prof is None:
                self.refresh_profiles(force=True)
                prof = self.profile(self.active_uuid)
            if prof and prof['name'] == HOTSPOT_CON:
                mode = 'hotspot'
            elif prof and prof['mode'] == 'ap':
                mode = 'other-ap'  # someone else's hotspot profile: treat it like ours
            else:
                mode = 'wifi'
        elif wlan[2].startswith('connecting'):
            mode = 'connecting'
        elif wlan[2] == 'unavailable':
            mode = 'unavailable'
        else:
            mode = 'disconnected'
        self.mode = mode

        self.wifi_ip = None
        if mode in ('wifi', 'hotspot', 'other-ap'):
            _, out, _ = nmcli('-g', 'IP4.ADDRESS', 'device', 'show', IFACE)
            self.wifi_ip = (out.split('|')[0].strip().split('/')[0]) or None
        self.clients = self.count_clients() if mode in ('hotspot', 'other-ap') else None
        return True

    def in_hotspot(self):
        return self.mode in ('hotspot', 'other-ap')

    def online(self):
        return self.mode == 'wifi' or self.wired

    def forced(self):
        return any(f.exists() for f in FORCE_FILES)

    def hotspot_in_use(self):
        return bool(self.clients) or time.monotonic() - self.last_ui_hit < UI_ACTIVE_WINDOW

    # -- actions on the radio

    def unblock_radio(self):
        run(['rfkill', 'unblock', 'wifi'], timeout=10)
        rc, out, _ = nmcli('radio', 'wifi')
        if rc == 0 and out.strip() != 'enabled':
            self.event('WiFi radio was off; turning it on')
            nmcli('radio', 'wifi', 'on')

    def ensure_hotspot_profile(self):
        f = profile_fields('id', HOTSPOT_CON, '802-11-wireless.ssid')
        if f is None:
            return False
        want = hotspot_ssid()
        if f.get('802-11-wireless.ssid') != want:
            self.event(f'Renaming hotspot to {want} to match the hostname')
            nmcli('connection', 'modify', 'id', HOTSPOT_CON, '802-11-wireless.ssid', want)
        return True

    def start_hotspot(self, reason):
        now = time.monotonic()
        if now < self.hotspot_retry_at:
            return False
        self.hotspot_retry_at = now + HOTSPOT_RETRY
        self.event(f'Starting hotspot {hotspot_ssid()}: {reason}')
        self.unblock_radio()
        if not self.ensure_hotspot_profile():
            self.event(f'No "{HOTSPOT_CON}" profile in NetworkManager; re-run the Ansible deploy')
            return False
        if not self.in_hotspot():
            self.refresh_scan(rescan=True)  # remember nearby networks for the page
        rc, _, err = nmcli('--wait', '30', 'connection', 'up', 'id', HOTSPOT_CON, 'ifname', IFACE, timeout=45)
        self.observe()
        if rc or self.mode != 'hotspot':
            self.event(f'Hotspot failed to start: {nmcli_error(err)}')
            return False
        self.last_probe = time.monotonic()
        self.event(f'Hotspot up: join "{hotspot_ssid()}", then open http://{HOTSPOT_ADDRESS}/network/')
        return True

    def stop_hotspot(self):
        if self.active_uuid:
            nmcli('connection', 'down', 'uuid', self.active_uuid, timeout=30)
        time.sleep(3)

    def activate(self, uuid):
        rc, _, err = nmcli('--wait', str(CONNECT_TIMEOUT), 'connection', 'up', 'uuid', uuid,
                           'ifname', IFACE, timeout=CONNECT_TIMEOUT + 20)
        self.observe()
        ok = rc == 0 and self.mode == 'wifi'
        if ok:
            return True, ''
        return False, nmcli_error(err) if rc else 'did not finish connecting'

    def settle(self, reason):
        """Every switch ends here: on WiFi, wired, or with the hotspot up."""
        self.observe()
        if self.online() or self.in_hotspot():
            return
        self.hotspot_retry_at = 0
        self.start_hotspot(reason)

    def probe(self, reason):
        """Drop the hotspot and try saved networks that are in range."""
        self.last_probe = time.monotonic()
        self.busy = 'Looking for saved WiFi networks'
        self.event(f'Trying saved WiFi networks ({reason})')
        try:
            self.stop_hotspot()
            self.refresh_scan(rescan=True)
            self.refresh_profiles(force=True)
            visible = {n['ssid']: n['signal'] for n in self.scan}
            candidates = sorted(
                (p for p in self.saved_networks() if p['autoconnect'] and (p['ssid'] in visible or p['hidden'])),
                key=lambda p: (-p['priority'], -visible.get(p['ssid'], 0)))
            if not candidates:
                self.event('No saved network in range')
            for p in candidates:
                ok, err = self.activate(p['uuid'])
                if ok:
                    self.event(f'Back on WiFi "{p["ssid"]}"')
                    return
                self.event(f'Could not join "{p["ssid"]}": {err}')
        finally:
            self.settle('WiFi retry failed')
            self.busy = None

    def join(self, ssid, password, hidden):
        """Add a profile for a new network and switch to it; undo if it fails."""
        self.busy = f'Connecting to "{ssid}"'
        self.last_attempt = {'ssid': ssid, 'status': 'trying', 'at': datetime.now().strftime('%b %d %H:%M:%S')}
        self.event(f'Joining "{ssid}" (requested from the page)')
        previous = self.active_uuid if self.mode == 'wifi' else None
        new_uuid = None
        try:
            if self.in_hotspot() or self.mode in ('connecting', 'disconnected'):
                self.stop_hotspot()
                self.refresh_scan(rescan=True)
            seen = next((n for n in self.scan if n['ssid'] == ssid), None)
            args = ['connection', 'add', 'type', 'wifi', 'ifname', IFACE, 'con-name', ssid, 'ssid', ssid,
                    'connection.autoconnect', 'yes']
            if password:
                wpa3_only = seen and 'WPA3' in seen['security'] and not re.search(r'WPA[12]', seen['security'])
                args += ['wifi-sec.key-mgmt', 'sae' if wpa3_only else 'wpa-psk', 'wifi-sec.psk', password]
            if hidden:
                args += ['802-11-wireless.hidden', 'yes']
            rc, out, err = nmcli(*args)
            m = re.search(r'\(([0-9a-f-]{36})\)', out)
            if rc or not m:
                raise RuntimeError(f'could not save network: {nmcli_error(err)}')
            new_uuid = m.group(1)

            ok, err = self.activate(new_uuid)
            if ok:
                self.refresh_profiles(force=True)
                for p in self.saved_networks():
                    if p['ssid'] == ssid and p['uuid'] != new_uuid:
                        nmcli('connection', 'delete', 'uuid', p['uuid'])  # replaced by the one that just worked
                self.last_attempt.update(status='ok', ip=self.wifi_ip)
                self.event(f'Joined "{ssid}" at {self.wifi_ip}')
                return
            raise RuntimeError(err)
        except RuntimeError as e:
            self.last_attempt.update(status='failed', error=str(e))
            self.event(f'Could not join "{ssid}": {e}')
            if new_uuid:
                nmcli('connection', 'delete', 'uuid', new_uuid)
            if previous:
                self.activate(previous)
        finally:
            self.refresh_profiles(force=True)
            self.settle(f'joining "{ssid}" failed')
            self.busy = None

    def forget(self, uuid):
        p = next((p for p in self.saved_networks() if p['uuid'] == uuid), None)
        if not p:
            return
        rc, _, err = nmcli('connection', 'delete', 'uuid', uuid)
        self.event(f'Forgot "{p["ssid"]}"' if rc == 0 else f'Could not forget "{p["ssid"]}": {nmcli_error(err)}')
        self.refresh_profiles(force=True)
        if self.mode == 'wifi' and uuid == self.active_uuid:
            self.offline_since = time.monotonic()

    # -- requests from the page (validated on the HTTP thread, run on the worker)

    def submit(self, body):
        action = body.get('action')
        if self.busy or not self.actions.empty():
            return 409, f'Busy: {self.busy or "another change is queued"}'
        if action == 'join':
            ssid = str(body.get('ssid', ''))
            password = str(body.get('password', ''))
            if not 1 <= len(ssid.encode()) <= 32:
                return 400, 'Network name must be 1-32 bytes'
            if password and not (8 <= len(password) <= 63 or re.fullmatch(r'[0-9a-fA-F]{64}', password)):
                return 400, 'WiFi passwords are 8-63 characters'
            self.actions.put(('join', ssid, password, bool(body.get('hidden'))))
        elif action == 'forget':
            uuid = str(body.get('uuid', ''))
            if not any(p['uuid'] == uuid for p in self.saved_networks()):
                return 400, 'Unknown network'
            self.actions.put(('forget', uuid))
        elif action == 'settings':
            try:
                values = clamp_settings(body.get('settings') or {})
            except (TypeError, ValueError):
                return 400, 'Settings must be whole numbers'
            self.actions.put(('settings', values))
        elif action in ('hotspot', 'wifi', 'scan'):
            self.actions.put((action,))
        else:
            return 400, 'Unknown action'
        return 202, 'OK'

    def handle(self, action):
        kind = action[0]
        if kind == 'join':
            self.join(*action[1:])
        elif kind == 'forget':
            self.forget(action[1])
        elif kind == 'settings':
            self.settings.update(action[1])
            try:
                save_settings(self.settings)
                self.event('Settings saved')
            except OSError as e:
                self.event(f'Could not save settings: {e}')
        elif kind == 'hotspot':
            self.hold_until = time.monotonic() + self.settings['manual_hold'] * 60
            if self.in_hotspot():
                self.event(f'Holding the hotspot for {self.settings["manual_hold"]} min')
            else:
                self.hotspot_retry_at = 0
                self.start_hotspot(f'requested from the page, held for {self.settings["manual_hold"]} min')
                self.settle('hotspot request failed')
        elif kind == 'wifi':
            self.hold_until = 0
            if self.in_hotspot():
                self.probe('requested from the page')
        elif kind == 'scan':
            if not self.in_hotspot():
                self.refresh_scan(rescan=True)

    # -- main loop

    def tick(self):
        now = time.monotonic()
        if not self.observe():
            self.mode = 'no-networkmanager'
            self.nm_fail_since = self.nm_fail_since or now
            if now - self.nm_fail_since > NM_RESTART_AFTER and now - self.nm_restarted_at > NM_RESTART_EVERY:
                self.event('NetworkManager is not answering; restarting it')
                self.nm_restarted_at = now
                run(['systemctl', 'restart', 'NetworkManager'], timeout=90)
            return
        self.nm_fail_since = None
        self.refresh_profiles()
        if self.mode in ('wifi', 'disconnected') and (self.scan_at is None or now - self.scan_at > SCAN_REFRESH):
            self.refresh_scan()

        forced = self.forced()
        if forced and not self.forced_logged:
            self.event('force-hotspot file found on the boot partition: keeping the hotspot up')
        self.forced_logged = forced

        if self.online() and not forced:
            self.offline_since = None
            return
        if self.offline_since is None:
            self.offline_since = now

        if self.in_hotspot():
            held = forced or now < self.hold_until
            if not held and now - self.last_probe >= self.settings['retry_interval']:
                if self.hotspot_in_use():
                    self.last_probe = now - self.settings['retry_interval'] + IN_USE_RECHECK
                else:
                    self.probe('scheduled retry')
            return

        if self.mode == 'missing':
            return
        if self.mode == 'unavailable' and now - self.radio_checked_at > 60:
            self.radio_checked_at = now
            self.unblock_radio()
        if forced:
            self.start_hotspot('force-hotspot file on the boot partition')
        elif self.wired:
            return
        elif now - self.offline_since >= self.settings['fallback_delay']:
            self.start_hotspot(f'no WiFi for {int(now - self.offline_since)}s')

    def status(self):
        now = time.monotonic()
        active = self.profile(self.active_uuid) if self.mode == 'wifi' else None
        hotspot_in = retry_in = hold_left = None
        if self.mode not in ('wifi', 'hotspot', 'other-ap') and not self.wired and self.offline_since is not None:
            hotspot_in = max(0, int(self.settings['fallback_delay'] - (now - self.offline_since)))
        if self.in_hotspot():
            if now < self.hold_until:
                hold_left = int(self.hold_until - now)
            retry_in = max(0, int(self.settings['retry_interval'] - (now - self.last_probe)))
        known = {p['ssid'] for p in self.saved_networks()}
        return {
            'hostname': socket.gethostname(),
            'mode': self.mode,
            'busy': self.busy,
            'wired': self.wired,
            'ip': self.wifi_ip,
            'wifi_ssid': active['ssid'] if active else None,
            'hotspot': {
                'ssid': hotspot_ssid(),
                'address': HOTSPOT_ADDRESS,
                'clients': self.clients,
                'in_use': self.in_hotspot() and self.hotspot_in_use(),
            },
            'hotspot_in': hotspot_in,
            'retry_in': retry_in,
            'hold_left': hold_left,
            'forced': self.forced(),
            'saved': [{k: p[k] for k in ('uuid', 'name', 'ssid', 'hidden', 'autoconnect', 'priority')}
                      | {'active': p['uuid'] == self.active_uuid} for p in self.saved_networks()],
            'scan': [dict(n, saved=n['ssid'] in known) for n in self.scan],
            'scan_age': int(now - self.scan_at) if self.scan_at else None,
            'settings': self.settings,
            'limits': LIMITS,
            'last_attempt': self.last_attempt,
            'events': list(self.events)[:40],
        }

    def run(self):
        self.event(f'Watching {IFACE}; fallback hotspot is "{hotspot_ssid()}"')
        self.unblock_radio()
        while True:
            try:
                action = self.actions.get(timeout=TICK)
            except queue.Empty:
                action = None
            try:
                if action:
                    self.handle(action)
                self.tick()
            except Exception:
                log.exception('Watchdog step failed')
                self.busy = None


# --- web page --------------------------------------------------------------

def make_handler(dog):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'plot-runner-wifi'

        def log_message(self, *args):
            pass

        def client_ip(self):
            ip = self.client_address[0]
            if ip == '127.0.0.1':  # behind nginx
                ip = self.headers.get('X-Real-IP', ip)
            return ip

        def reply(self, code, body, ctype='application/json'):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            dog.note_ui_hit(self.client_ip())
            path = self.path.split('?')[0]
            if path in ('/', '/index.html'):
                try:
                    self.reply(200, PAGE.read_bytes(), 'text/html; charset=utf-8')
                except OSError:
                    self.reply(500, b'index.html missing', 'text/plain')
            elif path == '/api/status':
                self.reply(200, dog.status())
            else:
                self.reply(404, {'error': 'not found'})

        def do_POST(self):
            dog.note_ui_hit(self.client_ip())
            if self.path.split('?')[0] != '/api/action':
                return self.reply(404, {'error': 'not found'})
            # JSON only: browsers can't send it cross-site without a CORS preflight, which we never allow
            if not self.headers.get('Content-Type', '').startswith('application/json'):
                return self.reply(415, {'error': 'send JSON'})
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(min(length, 4096)) or b'{}')
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                return self.reply(400, {'error': 'bad JSON'})
            code, msg = dog.submit(body)
            self.reply(code, {'ok': code < 300, 'message': msg} if code < 300 else {'error': msg})

    return Handler


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    dog = Watchdog()
    threading.Thread(target=dog.run, daemon=True, name='watchdog').start()
    while True:
        try:
            server = ThreadingHTTPServer((UI_HOST, UI_PORT), make_handler(dog))
            break
        except OSError as e:  # port busy: keep the watchdog running, retry the page
            log.error('Web page could not bind %s:%s (%s); retrying', UI_HOST, UI_PORT, e)
            time.sleep(30)
    log.info('Web page on http://%s:%s/', UI_HOST, UI_PORT)
    server.serve_forever()


if __name__ == '__main__':
    main()
