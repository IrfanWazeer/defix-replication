from routing import load_request


def request_value(text):
    return load_request(text)["value"]
