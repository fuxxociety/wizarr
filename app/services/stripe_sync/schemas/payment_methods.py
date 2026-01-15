from .types import EntitySchema


payment_methods_schema = EntitySchema(
    properties=[
        'id',
        'object',
        'created',
        'customer',
        'type',
        'billing_details',
        'metadata',
        'card',
    ]
)
