# Security policy

Report security issues privately to the repository owner rather than opening a public issue. Include the affected version, reproduction steps, and whether a crafted ROM or archive is required.

ForgeEmulation treats ROMs and ZIP files as untrusted input, rejects unsafe archive paths, caps scanned archive members at 128 MiB, and runs emulator cores outside the library process. This reduces risk but is not a sandbox. Only open files from sources you trust.

Version 1.0 is the supported security baseline.
