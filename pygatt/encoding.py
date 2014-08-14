import struct

INT8 = 0
UINT8 = 1
INT16 = 2
UINT16 = 3
INT32 = 4
UINT32 = 5
BOOL = 6
STRING = 7


def encode_bt_value(value, data_format):
    if data_format == INT8:
        return struct.pack('b', value)
    if data_format == UINT8:
        return struct.pack('B', value)
    if data_format == INT16:
        return struct.pack('h', value)
    if data_format == UINT16:
        return struct.pack('H', value)
    if data_format == INT32:
        return struct.pack('i', value)
    if data_format == UINT32:
        return struct.pack('I', value)
    if data_format == BOOL:
        return encode_bt_value(1 if value else 0, UINT8)
    raise NotImplemented


def decode_bt_value(value, data_format):
    if data_format == INT8:
        return struct.unpack('b', value)[0]
    if data_format == UINT8:
        return struct.unpack('B', value)[0]
    if data_format == INT16:
        return struct.unpack('h', value)[0]
    if data_format == UINT16:
        return struct.unpack('H', value)[0]
    if data_format == INT32:
        return struct.unpack('i', value)[0]
    if data_format == UINT32:
        return struct.unpack('I', value)[0]
    if data_format == STRING:
        return str(value.strip('\x00'))
    if data_format == BOOL:
        return bool(decode_bt_value(value, UINT8))
    raise NotImplemented