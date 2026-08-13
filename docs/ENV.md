# ENV.md — machine & toolchain of record

Captured at the initial contract freeze on the build machine. CI reproduces this on `ubuntu-latest`.

## Build machine (dev)
| Component | Value |
|---|---|
| OS | macOS 26.5 (build 25F71) |
| Arch | Apple Silicon (arm64) |
| Xcode CLT | `/Applications/Xcode.app/Contents/Developer` |
| Homebrew | 6.0.15 (`/opt/homebrew`) |
| Python | 3.12.13 (`~/.local/bin/python3.12`), project venv at `.venv/` |
| git | 2.50.1 |
| gh | 2.93.0 (authed as `billdmar`) |

## System libraries (Homebrew)
WeasyPrint needs native glib/pango/cairo/gdk-pixbuf. Installed via:
```bash
brew install pango gdk-pixbuf libffi   # cairo already present
```

### ⚠ macOS dyld note (portability-critical)
On Apple Silicon, Homebrew installs these under `/opt/homebrew/lib`, which is
**not** on the default dyld search path, so `import weasyprint` fails with
`OSError: cannot load library 'libgobject-2.0-0'` unless we point dyld at it:

```bash
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_FALLBACK_LIBRARY_PATH"
```

The report render path sets this automatically (see `src/report/`). On
`ubuntu-latest` the `apt-get` packages resolve on the normal loader path, so no
env var is needed there — that is why CI installs the `libpango*/libcairo2/...`
packages instead.

## Python environment
- Core + dev dependencies are pinned in `pyproject.toml` (determinism, the determinism requirement).
- Recreate:
  ```bash
  python3.12 -m venv .venv
  .venv/bin/pip install -e ".[dev]"
  ```

## SEC EDGAR fair-access
- Every request carries `User-Agent: thesis-research billdmar@gmail.com`.
- ≤10 req/s, 150ms spacing, on-disk cache under `data/fixtures/`.
- **CI never calls live EDGAR** — `THESIS_OFFLINE=1` and the `live` pytest
  marker is deselected. CI runs on committed fixtures only.

## LibreOffice (optional)
Not installed. Only needed as a fallback if the `formulas` recalc path can't
evaluate the workbook; install with `brew install --cask libreoffice` if G2
recalc requires it.
