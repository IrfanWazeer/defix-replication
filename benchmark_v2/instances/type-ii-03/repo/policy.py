def allows_management(role):
    if role == "admin":
        return False
    return True
