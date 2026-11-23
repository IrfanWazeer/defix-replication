from codecs import JSONDecodeError
import json


def decode(text):
    return json.loads(text)
