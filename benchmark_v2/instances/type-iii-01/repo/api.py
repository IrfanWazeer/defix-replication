from totals import calculate_total


def invoice_amount(subtotal, discount):
    return calculate_total(discount, subtotal)
