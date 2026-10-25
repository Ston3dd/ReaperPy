# ReaperPy v4.5 Enhanced

## Neue Erweiterungen
- **Function Caller**: GUI zur Eingabe der Zieladresse, RPC-Stub und bis zu sechs SysV-Registerargumente.
- **Call-Logger**: protokolliert Zeit, PID, Adresse, Stub, Argumente, RAX-Ergebnis und Fehlerstatus; Export als JSON/CSV.
- **Protokollmethode**: `PS5DebugClient.call_function()` implementiert `CMD_PROC_CALL` (`0xBDAA0006`) mit 68-Byte-Request und validierter PID-Antwort.
- **Bestätigungsdialog** vor dem RPC-Aufruf.
- **Tests** für Request-Layout, Rückgabewert, fehlende PID und Argumentgrenze.

## Wichtige Einschränkungen
- Die GUI setzt eine bereits aktive Verbindung und ausgewählte PID voraus.
- `rpcstub=0` ist nicht garantiert gültig; verwende nur einen gültigen Stub, der für deine Payload und das Ziel verfügbar ist. Das Kommando ist nicht risikofrei.
- Es wurde kein Live-Aufruf auf einer Konsole durchgeführt. Die Tests verwenden einen Mock und prüfen nur Protokollserialisierung/Antwortverarbeitung.
- Keine automatische Disassemblierung oder ABI-Signaturanalyse: Funktionsadresse und Argumenttypen müssen bekannt sein.

## Tests
`python -m compileall -q .`
`python -m unittest discover -s tests -v`
