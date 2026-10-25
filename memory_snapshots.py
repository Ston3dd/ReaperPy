"""Portable memory snapshot and diff primitives for ReaperPy.

The module deliberately has no network side effects. Callers provide bytes read
from a target process, making snapshots easy to test offline and safe to preview.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import json

@dataclass(frozen=True)
class Snapshot:
    address: int
    data: bytes
    label: str = ""
    captured_at: str = ""

    @classmethod
    def create(cls, address, data, label=""):
        if not isinstance(address, int) or address < 0:
            raise ValueError("address must be a non-negative integer")
        raw = bytes(data)
        if not raw:
            raise ValueError("snapshot data must not be empty")
        return cls(address, raw, str(label), datetime.now(timezone.utc).isoformat())

    def to_dict(self):
        return {"schema": 1, "address": self.address, "size": len(self.data),
                "data_hex": self.data.hex(), "label": self.label, "captured_at": self.captured_at}

    @classmethod
    def from_dict(cls, obj):
        if obj.get("schema") != 1:
            raise ValueError("Unsupported snapshot schema")
        data = bytes.fromhex(obj["data_hex"])
        if int(obj.get("size", len(data))) != len(data):
            raise ValueError("Snapshot size does not match payload")
        address = int(obj["address"])
        if address < 0 or not data:
            raise ValueError("Invalid snapshot address or empty payload")
        return cls(address, data, str(obj.get("label", "")), str(obj.get("captured_at", "")))

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

@dataclass(frozen=True)
class Change:
    address: int
    before: int
    after: int


def diff(before: Snapshot, after: Snapshot):
    """Return changed bytes at matching absolute addresses; unmatched tails are ignored."""
    start = max(before.address, after.address)
    end = min(before.address + len(before.data), after.address + len(after.data))
    if end <= start:
        return []
    a = before.data[start-before.address:end-before.address]
    b = after.data[start-after.address:end-after.address]
    return [Change(start+i, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y]
