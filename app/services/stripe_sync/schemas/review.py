from .types import EntitySchema


review_schema = EntitySchema(
    properties=[
        'id',
        'object',
        'billing_zip',
        'created',
        'charge',
        'closed_reason',
        'livemode',
        'ip_address',
        'ip_address_location',
        'open',
        'opened_reason',
        'payment_intent',
        'reason',
        'session',
    ]
)
