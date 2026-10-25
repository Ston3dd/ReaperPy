# ReaperPy v4.3 Enhanced — Upgrade notes

This upgrade keeps the existing ReaperPy v4.2 architecture and adds a **Watchlist / Freeze** tab in the Tools window.

## Added in this build

- Typed live watchlist for unsigned 8/16/32/64-bit values, signed 32-bit values, float32 and float64.
- Address input supports absolute addresses, `base`, and `base+0xOFFSET`.
- Previous/current value display for quick change tracking.
- Per-row freeze toggle (off by default); frozen values are written back only while Live-Überwachung is enabled.
- Manual typed write via double-click on a row value.
- CSV export of watch entries and latest values.
- Network access uses the existing `net_lock` so polling does not freely interleave with other tool commands.

## Feature comparison against PS5Debug-studio

The upstream repository describes features beyond the original ReaperPy v4.2: dedicated paged hex editor, function call logger, interactive function caller, richer cheat-step engine and item lists, `.ps5c` pack/share codes, `.shn`/`.mc4` export, frame-pointer-independent stack unwinding, XMM/FPU register UI, and a separate cheat-player app. ReaperPy already has memory read/write, scanner, pointer scan, debugger basics, disassembler/assembler support, code-cave patching, AOB tools, scripts, kernel log, projects and GoldHEN JSON export. This build adds the watchlist/freeze workflow but does **not** claim to have fully ported every upstream feature.

## Extra roadmap to go beyond the reference

1. Snapshot/diff engine with named baselines and address-region compare.
2. Safer patch transactions: preview, expected-byte checks, write verification and one-click rollback.
3. Plugin API for scanner strategies, file formats and debugger extensions.
4. Protocol capability detection and firmware compatibility matrix.
5. Test suite with mocked sockets, protocol packet fixtures, parser fuzz tests and CI.
6. Crash-safe session autosave, structured operation log and reproducible bug reports.
7. Disassembly xrefs, symbol labels and project-wide AOB signature health checks.
8. Export validation reports that explain unsupported dynamic steps instead of silently dropping them.

## Safety notes

Use only with consoles and software you own or are authorized to test. Memory writes and freezing can crash a game or console. Freeze is disabled by default and requires explicit user activation.

## Snapshot/diff core (developer API)

`memory_snapshots.py` adds an offline-testable, JSON-serializable snapshot primitive and byte-level diff function. It does not initiate network reads itself; the UI/client must explicitly read a region first, then pass those bytes to `Snapshot.create(...)`. This separation allows previews and unit tests without a connected console.
