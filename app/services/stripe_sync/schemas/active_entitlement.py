from .types import EntitySchema


active_entitlement_schema = EntitySchema(
    properties=['id', 'object', 'feature', 'lookup_key', 'livemode', 'customer']
)
