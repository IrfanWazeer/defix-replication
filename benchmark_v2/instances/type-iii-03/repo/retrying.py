def run_once(operation, attempts=0):
    for _ in range(attempts):
        if operation():
            return True
    return False
