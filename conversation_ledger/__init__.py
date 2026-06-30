"""Development shim so the src-layout package can run from the repo root."""

from pathlib import Path

_SRC_PACKAGE = Path(__file__).resolve().parent.parent / "src" / "conversation_ledger"
if _SRC_PACKAGE.is_dir():
    __path__.append(str(_SRC_PACKAGE))

__all__ = ["__version__"]
__version__ = "0.1.0"
