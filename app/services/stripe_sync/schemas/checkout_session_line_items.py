from .types import EntitySchema


checkout_session_line_item_schema = EntitySchema(
    properties=[
        'id',
        'object',
        'amount_discount',
        'amount_subtotal',
        'amount_tax',
        'amount_total',
        'currency',
        'description',
        'price',
        'quantity',
        'checkout_session',
    ]
)
