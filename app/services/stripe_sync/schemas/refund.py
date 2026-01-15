from .types import EntitySchema


refund_schema = EntitySchema(
    properties=[
        'id',
        'object',
        'amount',
        'balance_transaction',
        'charge',
        'created',
        'currency',
        'destination_details',
        'metadata',
        'payment_intent',
        'reason',
        'receipt_number',
        'source_transfer_reversal',
        'status',
        'transfer_reversal',
    ]
)
