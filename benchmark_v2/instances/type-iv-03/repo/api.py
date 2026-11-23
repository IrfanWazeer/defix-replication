from pathlib import Path


def setting_value():
    return (Path(__file__).parent / "resources" / "app.ini").read_text(encoding="utf-8").strip()
