def select_page(items, number, size):
    start = (number - 1) * (size - 1)
    return items[start:start + size]
