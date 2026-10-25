# ReaperPy v4.9 — Resumable Unreal Scan

- Universal Unreal analyzer supports incremental checkpoints, resume, progress callbacks, and cooperative cancellation.
- ZIP source counting uses archive metadata rather than decoding every source file before analysis.
- Checkpoints are stored outside the selected dump under `~/.reaperpy/unreal_scans/` and are validated against a source signature.
- UI adds progress, `ABBRECHEN`, `SCAN / FORTSETZEN`, and `NEU SCANNEN` controls.
- UI renders at most 5,000 rows to avoid freezing on large candidate reports; complete reports remain available through JSON/CSV export.
- Analyzer remains read-only static discovery. It does not assert that a candidate is a working cheat or perform memory writes.

Run tests: `python -m unittest discover -s tests -v`.
