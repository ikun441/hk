"""Keep the CRM bound to the current private IPv4 of one LAN interface."""
import ipaddress
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / '.env'
NETWORKS = tuple(ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
stopping = False


def request_stop(signum, frame):
    global stopping
    stopping = True


def private_address(interface):
    try:
        result = subprocess.run(['/usr/sbin/ipconfig', 'getifaddr', interface], capture_output=True, text=True, timeout=5)
        address = ipaddress.ip_address(result.stdout.strip())
        return str(address) if address.version == 4 and any(address in network for network in NETWORKS) else None
    except (ValueError, OSError, subprocess.TimeoutExpired):
        return None


def stop_child(child):
    if child and child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=12)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)


def main():
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    child = None
    current = None
    try:
        while not stopping:
            config = dotenv_values(ENV_FILE)
            interface = config.get('LAN_INTERFACE') or 'en0'
            target = private_address(interface)
            if target != current or (target and (child is None or child.poll() is not None)):
                stop_child(child)
                child = None
                current = target
                if target:
                    if config.get('HOST') != target:
                        set_key(ENV_FILE, 'HOST', target, quote_mode='never')
                        os.chmod(ENV_FILE, 0o600)
                    environment = dict(os.environ, HOST=target, PYTHONUNBUFFERED='1')
                    child = subprocess.Popen([sys.executable, str(ROOT / 'run.py')], cwd=ROOT, env=environment)
                    print(f'[LAN] {interface} -> {target}; server pid={child.pid}', flush=True)
                else:
                    print(f'[LAN] {interface}: waiting for a private IPv4 address', flush=True)
            time.sleep(3)
    finally:
        stop_child(child)


if __name__ == '__main__':
    main()
