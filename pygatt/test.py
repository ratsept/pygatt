import pygatt

a = pygatt.Adapter()
device = a.get_device('90:59:AF:15:C3:A9')
device.connect()
print device.set_characteristic('2b00', pygatt.UINT32, 34)
device.disconnect()
# for device in a.continuous_discovery():
#     device.connect()
#     print device.get_characteristic('2b00', pygatt.UINT32)
#     device.disconnect()