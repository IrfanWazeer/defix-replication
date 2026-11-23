from retrying import run_once


def run(operation):
    return run_once(operation)
