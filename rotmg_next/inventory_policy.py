"""Offline capacity calculation. Real inventory observation is deliberately absent."""

from dataclasses import dataclass


@dataclass(frozen=True)
class InventorySnapshot:
    capacity: int
    occupied: int
    reserved: int = 0

    def __post_init__(self) -> None:
        values = (self.capacity, self.occupied, self.reserved)
        if any(type(v) is not int for v in values):
            raise ValueError("inventory values must be integers")
        if self.capacity < 0 or self.occupied < 0 or self.reserved < 0:
            raise ValueError("inventory values cannot be negative")
        if self.occupied + self.reserved > self.capacity:
            raise ValueError("inventory occupancy and reservations exceed capacity")

    @property
    def free_slots(self) -> int:
        return self.capacity - self.occupied - self.reserved

    @property
    def can_receive(self) -> bool:
        return self.free_slots > 0
