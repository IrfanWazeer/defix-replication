from policy import allows_management


def may_manage(role):
    return allows_management(role)
