import sys
import time
import struct

import pygatt
from pygatt.bluetooth import Adapter, DEFAULT_ADAPTER, Device




def batch_lamps(adapter=DEFAULT_ADAPTER, mac_filter=None):
    global macs
    adapter = Adapter(adapter=adapter)

    def success(found_macs):
        global macs
        macs = found_macs

    def error():
        sys.exit("Error while searching for lamps")

    while True:
        adapter.do_discovery(mac_filter=mac_filter, success_callback=success, error_callback=error, max_seconds=1, min_seconds=.2)
        time.sleep(.5)
        for mac in macs:
            yield Device(mac)


def find_lamp_mac(adapter=DEFAULT_ADAPTER, mac_filter=None):
    global mac
    adapter = Adapter(adapter=adapter)
    mac = None

    def success(macs):
        global mac
        if not macs:
            sys.exit("Error - No lamps found")
        elif len(macs) > 1:
            sys.exit("Error - Multiple lamps found: %s" % ' '.join(macs))
        else:
            mac = macs[0]

    def error():
        sys.exit("Error while searching for lamps")

    adapter.do_discovery(mac_filter=mac_filter, success_callback=success, error_callback=error)
    return mac