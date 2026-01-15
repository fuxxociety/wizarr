from .types import EntitySchema


feature_schema = EntitySchema(
    properties=['id', 'object', 'livemode', 'name', 'lookup_key', 'active', 'metadata']
)
