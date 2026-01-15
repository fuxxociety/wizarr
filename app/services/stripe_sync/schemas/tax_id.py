from .types import EntitySchema


tax_id_schema = EntitySchema(
    properties=[
        'id',
        'country',
        'customer',
        'type',
        'value',
        'object',
        'created',
        'livemode',
        'owner',
    ]
)
