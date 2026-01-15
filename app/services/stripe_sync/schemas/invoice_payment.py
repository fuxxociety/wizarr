from .types import EntitySchema


invoice_payment_schema = EntitySchema(
    properties=[
        'id',
        'object',
        'amount_paid',
        'amount_requested',
        'created',
        'currency',
        'invoice',
        'is_default',
        'livemode',
        'payment',
        'status',
        'status_transitions',
    ]
)
