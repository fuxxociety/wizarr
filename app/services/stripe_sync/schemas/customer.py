from .types import EntitySchema


customer_schema = EntitySchema(
    properties=[
        'id',
        'object',
        'address',
        'description',
        'email',
        'metadata',
        'name',
        'phone',
        'shipping',
        'balance',
        'created',
        'currency',
        'default_source',
        'delinquent',
        'discount',
        'invoice_prefix',
        'invoice_settings',
        'livemode',
        'next_invoice_sequence',
        'preferred_locales',
        'tax_exempt',
    ]
)


customer_deleted_schema = EntitySchema(
    properties=['id', 'object', 'deleted']
)
