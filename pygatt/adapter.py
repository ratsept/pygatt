import re
import os
import stat
import signal
import time
from threading import Event, Thread
from datetime import datetime

from distutils.spawn import find_executable
import sh

from . import PygattException, Device


class Adapter(object):
    def __init__(self, hci_device='hci0', hcitool_path=None, gatttool_path=None):
        self.found_macs = []
        self.event = Event()
        self.hci_device = hci_device
        if hcitool_path is None:
            if 'HCITOOL_PATH' in os.environ:
                hcitool_path = os.environ['HCITOOL_PATH']
            else:
                hcitool_path = find_executable('hcitool')
            if hcitool_path is None or not os.path.isfile(hcitool_path):
                raise PygattException("hcitool not found")
        if os.geteuid() != 0 and not (os.stat(hcitool_path).st_mode & stat.S_ISUID):
            raise PygattException("You either must run pygatt as root or hcitool must be setuid root (sudo chmod u+s %s)" % hcitool_path)
        self.hcitool_path = hcitool_path

        if gatttool_path is None:
            if 'GATTTOOL_PATH' in os.environ:
                gatttool_path = os.environ['GATTTOOL_PATH']
            else:
                gatttool_path = find_executable('gatttool')
            if gatttool_path is None or not os.path.isfile(gatttool_path):
                raise PygattException("gatttool not found")
        if os.geteuid() != 0 and not (os.stat(gatttool_path).st_mode & stat.S_ISUID):
            raise PygattException("You either must run pygatt as root or gatttool must be setuid root (sudo chmod u+s %s)" % gatttool_path)
        self.gatttool_path = gatttool_path
        self.continue_discovery = None

    def stop_async_discovery(self):
        self.continue_discovery = False

    def discover_async(self, error_callback=None, success_callback=None, found_callback=None, max_seconds=2, min_seconds=0, mac_regex=None):
        self.continue_discovery = True
        SLEEP_SECONDS = .1
        MAC_RE = re.compile(r'^(?P<mac>([0-9A-F]{2}:){5}([0-9A-F]{2}))\s.*$', re.IGNORECASE)
        hcitool = sh.Command(self.hcitool_path)

        found_devices = []

        def callback(line):
            match = MAC_RE.match(line)
            if match:
                print 'FOUND'
                mac = match.groupdict()['mac']
                if (mac_regex is not None and not mac_regex.match(mac)) or mac in found_devices:
                    return
                found_devices.append(mac)
                if found_callback is not None:
                    found_callback(mac)

        process = hcitool('-i', self.hci_device, 'lescann', _bg=True, _out=callback)

        secs = 0
        while self.continue_discovery and secs < max_seconds and process.process.exit_code is None:
            if found_devices and secs > min_seconds:
                break

            time.sleep(SLEEP_SECONDS)
            secs += SLEEP_SECONDS

        if process.process.exit_code is None:
            process.signal(signal.SIGINT)

        try:
            process.wait()
        except sh.ErrorReturnCode:
            if error_callback is not None and self.continue_discovery:
                error_callback()
        else:
            if success_callback is not None and self.continue_discovery:
                success_callback(found_devices)

    def _success_callback(self, found_macs):
        self.found_macs = found_macs
        self.event.set()

    def _error_callback(self):
        self.event.set()

    def _found_callback(self, mac):
        pass

    def discover(self, max_seconds=2, min_seconds=0, mac_regex=None):
        print 'discover'
        self.found_macs = []
        self.event.clear()
        thread = Thread(
            target=self.discover_async,
            kwargs={
                'success_callback': self._success_callback,
                'error_callback': self._error_callback,
                'found_callback': self._found_callback,
                'max_seconds': max_seconds,
                'min_seconds': min_seconds,
                'mac_regex': mac_regex,
            }
        )
        thread.start()
        self.event.wait()
        return [Device(mac, self) for mac in self.found_macs]

    def continuous_discovery(self, mac_regex=None):
        last_device = None
        while True:
            devices = self.discover(mac_regex=mac_regex, max_seconds=1, min_seconds=0)
            for device in devices:
                if last_device is not None and last_device.disconnect_timestamp is not None and (datetime.utcnow() - last_device.disconnect_timestamp).total_seconds() < 3:
                    continue
                last_device = device
                yield device

    def __repr__(self):
        return '%s hci_device:%s' % (self.__class__, self.hci_device)