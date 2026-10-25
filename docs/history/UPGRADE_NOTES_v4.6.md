# ReaperPy v4.6 Enhanced — Static Analysis

## Added
- Read-only Static Analysis tab in the Tools window.
- Static direct-call graph extraction from a selected memory range.
- ASCII and UTF-16LE printable string extraction with CSV export.
- Optional disassembly listing for the selected range.
- Heuristic argument-register analysis API (`analysis_tools.infer_call_arguments`).
- Unit tests for string extraction, graph edges (when Capstone is installed), and argument hints.

## Limits
- This is static, heuristic analysis, not a complete decompiler.
- Direct call graph only includes direct `call` targets within the selected range. Indirect calls, tail calls, symbol recovery, and reliable function boundaries require additional metadata or deeper control-flow analysis.
- Argument-register hints are not authoritative types; the x86-64 ABI and compiler optimization can make source-level types impossible to infer from a small window.
- Analysis reads target memory only; it does not execute code or write memory.
- Live PS5 validation has not been performed.

## Test
`python -m unittest discover -s tests -v`
