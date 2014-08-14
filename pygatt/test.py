from time import sleep
from pygatt import Adapter

a = Adapter()
for device in a.discover():
    device.connect()
    sleep(1)
    device.disconnect()