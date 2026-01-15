from typing import List
from dataclasses import dataclass


@dataclass(frozen=True)
class EntitySchema:
    """Schema definition for a Stripe entity."""
    properties: List[str]
