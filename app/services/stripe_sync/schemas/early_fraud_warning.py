from .types import EntitySchema


early_fraud_warning_schema = EntitySchema(
    properties=[
        'id',
        'object',
        'actionable',
        'charge',
        'created',
        'fraud_type',
        'livemode',
        'payment_intent',
    ]
)
