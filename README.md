# pygatt

### Installation

You can install `pygatt` directly from github:

```
pip install git+https://github.com/Sonopro/pygatt.git
```

### Requirements

Pygatt has been tested to work with the version of `bluez` included in Ubuntu 14.04- there is no need to compile `bluez` manually.  Pygatt requires [`sh`](https://github.com/amoffat/sh) but it should be automatically installed by pip.

You must run any scripts that use pygatt as `root` or alternatively you must `setuid` the `hcitoool` and `gatttool` executables:
```
sudo chmod u+s /usr/bin/hcitool
sudo chmod u+s /usr/bin/gatttool
```

### Basic usage

##### Performing a single discovery and listing MAC addresses of discoverable BT 4.0 devices:

```python
import pygatt
adapter = pygatt.Adapter()
for device in adapter.discover():
    print device.mac
```

##### Performing a single discovery and printing a specific characteristic of discovered devices(s):

```python
import pygatt
adapter = pygatt.Adapter()
for device in adapter.discover():
    device.connect()
    print device.get_characteristic('2b00', pygatt.UINT32)
    device.disconnect()
```

##### Connect to a specific device and set a characteristic:
```python
import pygatt
adapter = pygatt.Adapter()
device = adapter.get_device('90:59:AF:15:C3:A9')
device.connect()
device.set_characteristic('2b00', pygatt.UINT32, 1024)
device.disconnect()
```

##### Perform continuous discovery:
```python
import pygatt
adapter = pygatt.Adapter()
for device in adapter.continuous_discovery():
    device.connect()
    device.set_characteristic('2b00', pygatt.UINT32, 1024)
    device.disconnect()
```

End continuous discovery with a `Ctrl-C`


### Advanced usage

##### Specify a specific HCI device:

If you don't explicitly specify a device `pygatt` will attempt to use `hci0`.

To specify a different device you can set the `HCI_DEVICE` environmental variable:

```
export HCI_DEVICE=hci1
```

Alternatively you can pass a `hci_device` argument when you instantiate the adapter:

```python
adapter = pygatt.Adapter(hci_device='hci1')
```