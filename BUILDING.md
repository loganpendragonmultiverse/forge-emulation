# Building on Windows

ForgeEmulation targets Windows 10/11 x64 and Python 3.12.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe scripts\fetch_cores.py
.\scripts\build_release.ps1
```

`fetch_cores.py` accepts only the hashes recorded in `third_party/core-manifest.json`. If the upstream mutable buildbot URL changes, the command fails closed; review and retest a replacement before changing the manifest.

The release script runs static checks and the full suite before creating `release/ForgeEmulation-1.0.0-windows-x64.zip`. The package includes the four core DLLs, their license texts, and the pinned source snapshots required to reproduce and inspect them.

Do not place copyrighted ROMs or proprietary firmware in the repository, test fixtures, or release package.
