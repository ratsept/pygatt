import pygatt

a = pygatt.Adapter()
for device in a.continuous_discovery():
    device.connect()
    print device.get_characteristic('2b00', pygatt.UINT32)
    device.disconnect()