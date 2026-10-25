"""buildtools.py - Hilfen fuer den EXE-Bau (build_exe.bat): Windows-Versionsinfo aus version.py erzeugen.

    python buildtools.py          schreibt version_info.txt (von ReaperPy.spec benutzt)
"""
import os

import version

HERE = os.path.dirname(os.path.abspath(__file__))


def version_info_text(ver=None, name=None, description="ReaperPy - PS5 Memory Tools"):
    ver = ver or version.__version__
    name = name or version.APP_NAME
    nums = [int(x) for x in (ver.split("-")[0].split(".") + ["0", "0", "0"])[:3]] + [0]
    t = tuple(nums)
    dotted = ".".join(str(x) for x in t)
    return f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', ''),
      StringStruct('FileDescription', '{description}'),
      StringStruct('FileVersion', '{dotted}'),
      StringStruct('InternalName', '{name}'),
      StringStruct('OriginalFilename', '{name}.exe'),
      StringStruct('ProductName', '{name}'),
      StringStruct('ProductVersion', '{dotted}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def write_version_file(path=None):
    path = path or os.path.join(HERE, "version_info.txt")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(version_info_text())
    return path


if __name__ == "__main__":
    print(write_version_file())
