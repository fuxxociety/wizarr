from .types import EntitySchema


subscription_schedule_schema = EntitySchema(
    properties=[
        'id',
        'object',
        'application',
        'canceled_at',
        'completed_at',
        'created',
        'current_phase',
        'customer',
        'default_settings',
        'end_behavior',
        'livemode',
        'metadata',
        'phases',
        'released_at',
        'released_subscription',
        'status',
        'subscription',
        'test_clock',
        'billing_mode',
    ]
)
