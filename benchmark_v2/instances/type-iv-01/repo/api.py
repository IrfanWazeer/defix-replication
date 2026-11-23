import os


def listener_port():
    return int(os.environ["APP_PORT"])
