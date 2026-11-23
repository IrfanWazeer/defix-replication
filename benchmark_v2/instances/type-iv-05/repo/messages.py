from pathlib import Path


def read_message():
    return Path("resources/message.txt").read_text(encoding="utf-8").strip()
