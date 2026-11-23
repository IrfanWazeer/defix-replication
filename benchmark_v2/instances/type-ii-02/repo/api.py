from pricing import shipping_cost


def order_shipping(quantity, express):
    return shipping_cost(quantity, express)
