# ReaperPy v5.1 — Large Dump Reliability

## Changes
- Increased supported individual source size from 25 MB to 128 MB so large dumper exports such as `GObjects.txt` are included instead of silently ignored.
- ZIP scans deduplicate identical payloads by ZIP CRC and uncompressed size, avoiding repeated analysis of duplicated SDK exports bundled under multiple paths.
- ZIP progress totals now count unique eligible payloads, matching the scan iterator.
- Resumed scans rebuild category counters from checkpointed hits, so summary counts are consistent after continuing a partial scan.
- Added tests for duplicate ZIP payloads and resumed summary consistency.

## Scope and limitations
- Static, read-only analysis only. A candidate is not a validated runtime cheat.
- Source files larger than 128 MB are still excluded as a defensive limit.
- Deduplicating byte-identical ZIP members keeps the first lexicographically sorted path as the evidence source; duplicate paths are not separately represented.
- Runtime memory writes, game function invocation, and automatic activation remain out of scope.

## Test
`python -m unittest discover -s tests -v`
