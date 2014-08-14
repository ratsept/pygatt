import binascii
import re
import time
import sh
from Queue import Queue
from threading import Event, Thread

from . import PygattException, encode_bt_value, decode_bt_value
from .utils import standardize_uuid


class ConnectionException(PygattException):
    pass


class TimeoutException(PygattException):
    pass


class Device(object):
    DEFAULT_TIMEOUT = 3
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

        self.event = Event()

    def quit(self):
        self.connected = False
        self.to_gatt.put('quit\n')

    def set_characteristic_async(self, uuid, data_format, value, callback):
        uuid = standardize_uuid(uuid)
        self.set_characteristic_callback = callback
        handle = self.uuid_to_handle_map[uuid]
        self.to_gatt.put('char-write-req %s %s\n' % (handle, binascii.hexlify(encode_bt_value(value, data_format))))

    def get_characteristic_async(self, uuid, data_format, callback):
        uuid = standardize_uuid(uuid)
        self.get_characteristic_callback = callback
        self._current_decoder = lambda x: decode_bt_value(x, data_format)
        self.to_gatt.put('char-read-uuid %s\n' % uuid)

    def connect_async(self, connected_callback=None, error_callback=None, disconnected_callback=None):
        sleep_seconds = .1
        connect_timeout = 2
        self.connected_callback = connected_callback
        self.error_callback = error_callback
        self.disconnected_callback = disconnected_callback

        if self.connected:
            return

        to_gatt = Queue()
        self.to_gatt = to_gatt

        def out_callback(line):
            print line
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
                self.handle_uuid_map_timer = sleep_seconds * 3
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
            time.sleep(sleep_seconds)
            if not self.connected:
                if connect_timeout <= 0:
                    self.quit()
                    if self.error_callback is not None:
                        self.error_callback()
                connect_timeout -= sleep_seconds
            if self.connected_callback is not None:
                if self.handle_uuid_map_timer <= 0:
                    self.connected_callback()
                    self.connected_callback = None
                else:
                    self.handle_uuid_map_timer -= sleep_seconds
        try:
            process.wait()
        except sh.ErrorReturnCode:
            if self.error_callback is not None:
                self.error_callback()

    def disconnect(self):
        self.quit()

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

    def get_characteristic(self, uuid, data_format, timeout=DEFAULT_TIMEOUT):
        self.event.clear()
        if not self.connected:
            raise ConnectionException("Error - Not connected")
        self.get_characteristic_async(uuid, data_format, self._get_callback)
        if not self.event.wait(timeout):
            raise TimeoutException("Bluetooth get_characteristic timed out")
        return self.value

    def set_characteristic(self, uuid, data_format, value, timeout=DEFAULT_TIMEOUT):
        self.event.clear()
        if not self.connected:
            raise ConnectionException("Error - Not connected")
        self.set_characteristic_async(uuid, data_format, value, self._set_callback)
        if not self.event.wait(timeout):
            raise TimeoutException("Bluetooth set_characteristic timed out")

    def connect(self, timeout=DEFAULT_TIMEOUT):
        self.event.clear()
        thread = Thread(
            target=self.connect_async,
            kwargs={
                'connected_callback': self._connected_callback,
                'error_callback': self._error_callback,
                'disconnected_callback': self._disconnected_callback
            }
        )
        thread.start()

        if not self.event.wait(timeout):
            self.quit()
            raise ConnectionException("Connection timed out")

        if not self.connected:
            self.quit()
            raise ConnectionException("Unable to connect")

    def __repr__(self):
        return '%s mac:%s' % (self.__class__, self.mac)