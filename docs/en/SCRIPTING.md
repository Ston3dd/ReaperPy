# Scripting

The `ps5` object for Python scripts.

[← Back to the README](../../README.md)

---

## Scripting

```python
base = ps5.module()                                  # base of eboot.bin
hp   = ps5.pointer(base + 0x4A1C00, 0x20, 0x1C4)     # resolve a pointer path
if hp:
    ps5.write_u32(hp, 999, undo=True)                # undo_all() restores it
site = ps5.aob("48 8B 05 ?? ?? ?? ?? 8B 40 1C")
if site:
    ps5.nop(site, 6)                                 # NOP with undo
```

Also available: `ps5.call()`, `ps5.foreground()`, `ps5.write_many()`, `ps5.log_calls()`, `ps5.alloc()`.
