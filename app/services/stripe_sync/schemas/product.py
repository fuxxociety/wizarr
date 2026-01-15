from .types import EntitySchema


product_schema = EntitySchema(
    properties=[
        'id',
        'object',
        'active',
        'default_price',
        'description',
        'metadata',
        'name',
        'created',
        'images',
        'marketing_features',
        'livemode',
        'package_dimensions',
        'shippable',
        'statement_descriptor',
        'unit_label',
        'updated',
        'url',
    ]
)
