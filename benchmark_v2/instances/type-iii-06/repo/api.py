from storage import lookup


def value_for(key, entries):
    result = lookup(key, entries)
    return result.upper()
