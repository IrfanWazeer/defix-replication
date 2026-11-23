from os.path import PurePath


def normalize(value):
    return str(PurePath(value))
