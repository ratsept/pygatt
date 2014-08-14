def standardize_uuid(uuid):
    if isinstance(uuid, int):
        uuid = '%04x' % uuid
    if len(uuid) == 4:
        return '0000%s-0000-1000-8000-00805f9b34fb' % uuid.lower()
    return uuid.lower()