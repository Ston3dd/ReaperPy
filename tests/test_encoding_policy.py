"""Wächter: Textdateien werden immer mit explizitem Encoding geöffnet (sonst gilt unter Windows cp1252)."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _offences(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    bad = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        kws = {k.arg for k in n.keywords}
        name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
        if name == "open" and (isinstance(f, ast.Name) or (isinstance(f.value, ast.Name) and f.value.id == "io")):
            mode = n.args[1] if len(n.args) > 1 else next((k.value for k in n.keywords if k.arg == "mode"), None)
            m = mode.value if isinstance(mode, ast.Constant) and isinstance(mode.value, str) else "r"
            if "b" not in m and "encoding" not in kws and len(n.args) < 4:
                bad.append((n.lineno, "open() ohne encoding"))
        elif name in ("read_text", "write_text") and "encoding" not in kws:
            bad.append((n.lineno, f"{name}() ohne encoding"))
        elif name in ("run", "check_output", "Popen") and "text" in kws and "encoding" not in kws:
            bad.append((n.lineno, "subprocess text=True ohne encoding"))
    return bad


class EncodingPolicy(unittest.TestCase):
    def test_no_implicit_text_encoding(self):
        problems = []
        for p in sorted(ROOT.glob("*.py")) + sorted((ROOT / "tests").glob("*.py")):
            problems += [f"{p.relative_to(ROOT)}:{ln}: {msg}" for ln, msg in _offences(p)]
        self.assertEqual(problems, [], "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
