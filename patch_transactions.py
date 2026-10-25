"""Transactional memory patch helpers for ReaperPy.

No network side effects: callers provide read/write functions. Every write checks
expected bytes, verifies the result, and attempts rollback if verification fails.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import json

@dataclass
class PatchResult:
    address: int
    before: bytes
    after: bytes
    timestamp: str
    rolled_back: bool = False

class PatchConflict(RuntimeError):
    pass

class PatchTransaction:
    def __init__(self, read_memory, write_memory):
        self.read_memory = read_memory
        self.write_memory = write_memory
        self.history = []

    def apply(self, address: int, replacement: bytes, expected: bytes | None = None) -> PatchResult:
        if not isinstance(address, int) or address < 0:
            raise ValueError('Adresse muss eine nicht-negative Ganzzahl sein')
        replacement = bytes(replacement)
        if not replacement:
            raise ValueError('Patch darf nicht leer sein')
        before = bytes(self.read_memory(address, len(replacement)))
        if len(before) != len(replacement):
            raise IOError(f'Unvollständiger Lesezugriff: {len(before)} statt {len(replacement)} Byte')
        if expected is not None and before != bytes(expected):
            raise PatchConflict(f'Bytes geändert: erwartet {bytes(expected).hex(" ")}, gefunden {before.hex(" ")}')
        self.write_memory(address, replacement)
        after = bytes(self.read_memory(address, len(replacement)))
        if after != replacement:
            try:
                self.write_memory(address, before)
                rolled = bytes(self.read_memory(address, len(before))) == before
            except Exception:
                rolled = False
            result = PatchResult(address, before, replacement, datetime.now(timezone.utc).isoformat(), rolled)
            self.history.append(result)
            raise IOError('Write-Verifikation fehlgeschlagen' + ('; Rollback erfolgreich' if rolled else '; Rollback fehlgeschlagen'))
        result = PatchResult(address, before, replacement, datetime.now(timezone.utc).isoformat())
        self.history.append(result)
        return result

    def rollback(self, result: PatchResult):
        current = bytes(self.read_memory(result.address, len(result.after)))
        if current != result.after:
            raise PatchConflict('Rollback verweigert: Speicher entspricht nicht mehr dem angewendeten Patch')
        self.write_memory(result.address, result.before)
        if bytes(self.read_memory(result.address, len(result.before))) != result.before:
            raise IOError('Rollback konnte nicht verifiziert werden')
        result.rolled_back = True

    def export_history(self, path):
        payload = {'schema': 1, 'history': [
            {'address': f'0x{x.address:X}', 'before': x.before.hex(), 'after': x.after.hex(),
             'timestamp': x.timestamp, 'rolled_back': x.rolled_back} for x in self.history]}
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
