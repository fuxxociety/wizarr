from .types import EntitySchema


credit_note_schema = EntitySchema(
    properties=[
        'id',
        'object',
        'amount',
        'amount_shipping',
        'created',
        'currency',
        'customer',
        'customer_balance_transaction',
        'discount_amount',
        'discount_amounts',
        'invoice',
        'lines',
        'livemode',
        'memo',
        'metadata',
        'number',
        'out_of_band_amount',
        'pdf',
        'reason',
        'refund',
        'shipping_cost',
        'status',
        'subtotal',
        'subtotal_excluding_tax',
        'tax_amounts',
        'total',
        'total_excluding_tax',
        'type',
        'voided_at',
    ]
)
