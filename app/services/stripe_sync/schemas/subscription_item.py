from .types import EntitySchema


subscription_item_schema = EntitySchema(
    properties=[
        'id',
        'object',
        'billing_thresholds',
        'created',
        'deleted',
        'metadata',
        'quantity',
        'price',
        'subscription',
        'tax_rates',
        'current_period_end',
        'current_period_start',
    ]
)
