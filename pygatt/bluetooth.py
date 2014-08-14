import binascii
import struct
import re
import os
import signal
import time
import sh
from Queue import Queue
from threading import Event, Thread
from distutils.spawn import find_executable

UNSIGNED_INT32 = (lambda x: struct.unpack('I', x)[0], lambda x: struct.pack('I', x))
UNSIGNED_INT16 = (lambda x: struct.unpack('H', x)[0], lambda x: struct.pack('H', x))
INT16 = (lambda x: struct.unpack('h', x)[0], lambda x: struct.pack('h', x))
INT8 = (lambda x: struct.unpack('b', x)[0], lambda x: struct.pack('b', x))
UNSIGNED_INT8 = (lambda x: struct.unpack('B', x)[0], lambda x: struct.pack('B', x))
STRING = (lambda x: str(x.strip('\x00')), None)


class PygattException(Exception):
    pass


class Adapter(object):
    def __init__(self, hci_device='hci0', hcitool_path=None, gatttool_path=None):
        self.hci_device = hci_device
        if hcitool_path is None:
            if 'HCITOOL_PATH' in os.environ:
                hcitool_path = os.environ['HCITOOL_PATH']
            else:
                hcitool_path = find_executable('hcitool')
            if hcitool_path is None or not os.path.isfile(hcitool_path):
                raise PygattException("hcitool not found")
        self.hcitool_path = hcitool_path

        if gatttool_path is None:
            if 'GATTTOOL_PATH' in os.environ:
                gatttool_path = os.environ['GATTTOOL_PATH']
            else:
                gatttool_path = find_executable('gatttool')
            if gatttool_path is None or not os.path.isfile(gatttool_path):
                raise PygattException("gatttool not found")
        self.gatttool_path = gatttool_path
        self.continue_discovery = None

    def stop_discovery(self):
        self.continue_discovery = False

    def do_discovery(self, error_callback=None, success_callback=None, found_callback=None, max_seconds=2, min_seconds=0, mac_regex=None):
        self.continue_discovery = True
        SLEEP_SECONDS = .1
        MAC_RE = re.compile(r'^(?P<mac>([0-9A-F]{2}:){5}([0-9A-F]{2}))\s.*$', re.IGNORECASE)
        hcitool = sh.Command(self.hcitool_path)

        found_devices = []

        def callback(line):
            match = MAC_RE.match(line)
            if match:
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


class AsyncDevice(object):
    CHAR_VALUE_RE = re.compile(r'.*?handle: 0x[0-9a-f]+\s+value: (?P<value>([0-9a-f]{2}\s?)+)\s*$', re.IGNORECASE)
    CHAR_RE = re.compile(
        r'^.*?handle: 0x[0-9a-f]+, char properties: 0x[0-9a-f]+, char value handle: (?P<handle>0x[0-9a-f]+), uuid: (?P<uuid>[a-z0-9-]+)\s*$',
        re.IGNORECASE
    )

    def __init__(self, mac, adapter):
        self.mac = mac
        self.adapter = adapter
        self.to_gatt = None
        self.connected = False
        self.uuid_to_handle_map = {}
        self.handle_uuid_map_timer = 100

        self._current_decoder = None

        self.connected_callback = None
        self.error_callback = None
        self.disconnected_callback = None
        self.get_characteristic_callback = None
        self.set_characteristic_callback = None
        self.process = None

    @staticmethod
    def standardize_uuid(uuid):
        if isinstance(uuid, int):
            uuid = '%04x' % uuid
        if len(uuid) == 4:
            return '0000%s-0000-1000-8000-00805f9b34fb' % uuid.lower()
        return uuid.lower()

    def quit(self):
        self.connected = False
        self.to_gatt.put('quit\n')

    def set_characteristic(self, uuid, format, value, callback):
        uuid = self.standardize_uuid(uuid)
        self.set_characteristic_callback = callback
        handle = self.uuid_to_handle_map[uuid]
        decoder, encoder = format
        self.to_gatt.put('char-write-req %s %s\n' % (handle, binascii.hexlify(encoder(value))))

    def get_characteristic(self, uuid, format, callback):
        uuid = self.standardize_uuid(uuid)
        self.get_characteristic_callback = callback
        decoder, encoder = format
        self._current_decoder = decoder
        self.to_gatt.put('char-read-uuid %s\n' % uuid)

    def set_disconnected_callback(self, callback):
        self.disconnected_callback = callback

    def set_error_callback(self, callback):
        self.error_callback = callback

    def connect(self, connected_callback=None, error_callback=None, disconnected_callback=None):
        SLEEP_SECONDS = .1
        connect_timeout = 2
        self.connected_callback = connected_callback
        self.error_callback = error_callback
        self.disconnected_callback = disconnected_callback

        if self.connected:
            return

        to_gatt = Queue()
        self.to_gatt = to_gatt

        def out_callback(line):
            if '**' in line:
                if self.connected and line.startswith('[%s]' % self.mac):
                    if self.disconnected_callback is not None:
                        self.disconnected_callback()
                    self.quit()
            elif 'Error' in line:
                error_callback(line)
            elif 'connection successful' in line.lower():
                to_gatt.put('characteristics\n')
                self.connected = True
            elif any(x in line for x in ('Attempting to connect', 'char-read-uuid', 'quit', 'connect', 'characteristics')):
                pass
            elif 'char value handle' in line:
                match = self.CHAR_RE.match(line)
                group_dict = match.groupdict()
                self.uuid_to_handle_map[group_dict['uuid']] = group_dict['handle']
                self.handle_uuid_map_timer = SLEEP_SECONDS * 3
            elif 'value: ' in line:
                match = self.CHAR_VALUE_RE.match(line)
                value = match.groupdict()['value']
                self.get_characteristic_callback(
                    self._current_decoder(
                        binascii.unhexlify(value.replace(' ', '').strip())
                    )
                )
            elif 'written successfully' in line:
                self.set_characteristic_callback()

        def error_callback(line):
            if self.error_callback is not None:
                self.error_callback()
            self.quit()

        gatttool = sh.Command(self.adapter.gatttool_path)
        process = gatttool('-i', self.adapter.hci_device, '-b', self.mac, '-I',
                           _bg=True, _out=out_callback, _err=error_callback, _in=to_gatt)
        self.process = process
        to_gatt.put('connect\n')
        while process.process.exit_code is None:
            to_gatt.put('**\n')
            time.sleep(SLEEP_SECONDS)
            if not self.connected:
                if connect_timeout <= 0:
                    self.quit()
                    if self.error_callback is not None:
                        self.error_callback()
                connect_timeout -= SLEEP_SECONDS
            if self.connected_callback is not None:
                if self.handle_uuid_map_timer <= 0:
                    self.connected_callback()
                    self.connected_callback = None
                else:
                    self.handle_uuid_map_timer -= SLEEP_SECONDS
        try:
            process.wait()
        except sh.ErrorReturnCode:
            if self.error_callback is not None:
                self.error_callback()


class ConnectionException(PygattException):
    pass


class TimeoutException(PygattException):
    pass


class Device(object):
    GET_TIMEOUT = 2
    SET_TIMEOUT = GET_TIMEOUT
    CONNECT_TIMEOUT = 6

    def __init__(self, mac):
        self.mac = mac
        self.event = Event()
        self.async_device = AsyncDevice(mac)
        self.value = None
        self.connected = False

    def connect(self):
        self.event.clear()
        thread = Thread(
            target=self.async_device.connect,
            kwargs={
                'connected_callback': self._connected_callback,
                'error_callback': self._error_callback,
                'disconnected_callback': self._disconnected_callback
            }
        )
        thread.start()

        if not self.event.wait(self.CONNECT_TIMEOUT):
            raise ConnectionException("Connection timed out")

        if not self.connected:
            raise ConnectionException("Unable to connect")

    def disconnect(self):
        self.async_device.quit()

    def _disconnected_callback(self):
        self.connected = False
        self.event.set()

    def _connected_callback(self):
        self.connected = True
        self.event.set()

    def _error_callback(self):
        self.event.set()
        self.connected = False

    def _get_callback(self, char):
        self.value = char
        self.event.set()

    def _set_callback(self):
        self.event.set()

    def get_characteristic(self, uuid, format):
        if not self.connected:
            raise ConnectionException("Error - Not connected")
        self.async_device.get_characteristic(uuid, format, self._get_callback)
        if not self.event.wait(self.GET_TIMEOUT):
            raise TimeoutException("Bluetooth get_characteristic timed out")
        self.event.clear()
        return self.value

    def set_characteristic(self, uuid, format, value):
        if not self.connected:
            raise ConnectionException("Error - Not connected")
        self.async_device.set_characteristic(uuid, format, value, self._set_callback)
        if not self.event.wait(self.SET_TIMEOUT):
            raise TimeoutException("Bluetooth set_characteristic timed out")
        self.event.clear()