import os


def records_directory():
    return os.getenv("DATA_ROOT", "/srv/records")
