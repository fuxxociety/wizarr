from .types import EntitySchema


setup_intents_schema = EntitySchema(
    properties=[
        'id',
        'object',
        'created',
        'customer',
        'description',
        'payment_method',
        'status',
        'usage',
        'cancellation_reason',
        'latest_attempt',
        'mandate',
        'single_use_mandate',
        'on_behalf_of',
    ]
)
