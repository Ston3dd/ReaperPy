# ReaperPy v4.4 Enhanced — Hex Editor & Transactional Patching

## Added

- Paged hex editor (up to 4 KiB per page) with address navigation and byte display.
- Hex-pattern search within the loaded page.
- Row-level byte editing with a confirmation preview.
- Patch transaction helper that captures original bytes, checks expected bytes, verifies writes, and supports guarded rollback.
- Baseline snapshot and byte-level diff view.
- JSON snapshot export and patch history JSON export API.
- Offline unit tests for apply/rollback/conflict behavior.

## Safety and limitations

- The editor is designed for authorized debugging of software/hardware you control.
- Writes may crash a process or console. The UI confirms each edit, checks original bytes and verifies the result.
- Rollback is refused if the current bytes no longer match the patch, to avoid overwriting later changes.
- This build does not claim full PS5Debug-studio protocol parity. Function-call/RPC operations must only be added after verifying the exact API exposed by the connected payload/client version.
- No live PS5 connection was available for hardware testing.

## Tests

Run from the `ReaperPy` directory:

```bash
python -m unittest discover -s tests -v
python -m compileall -q .
```
