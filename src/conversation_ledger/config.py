from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from conversation_ledger.platforms import ALLOWED_PLATFORMS


def _split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(slots=True)
class LedgerConfig:
    commons_root: Path
    data_root: Path
    knowledge_root: Path
    output_root: Path
    collector_host: str = "127.0.0.1"
    collector_port: int = 8765
    collector_token: str = ""
    allow_platforms: tuple[str, ...] = ALLOWED_PLATFORMS
    allow_projects: tuple[str, ...] = ()

    @property
    def inbox_path(self) -> Path:
        return self.data_root / "inbox"

    @property
    def raw_root(self) -> Path:
        return self.data_root / "raw"

    @property
    def imports_original_root(self) -> Path:
        return self.data_root / "imports" / "original"

    @property
    def normalized_root(self) -> Path:
        return self.data_root / "normalized"

    @property
    def index_root(self) -> Path:
        return self.data_root / "index"

    @property
    def db_path(self) -> Path:
        return self.index_root / "conversations.sqlite"

    @property
    def exports_root(self) -> Path:
        return self.data_root / "exports"

    def ensure_directories(self) -> None:
        for path in (
            self.data_root,
            self.inbox_path,
            self.raw_root,
            self.imports_original_root,
            self.normalized_root,
            self.index_root,
            self.exports_root,
            self.output_root,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls, repo_root: Path | None = None) -> "LedgerConfig":
        repo_root = repo_root or Path.cwd()
        _load_dotenv(repo_root / ".env")

        commons_root = Path(os.environ.get("COMMONS_ROOT", "E:/commons"))
        data_root = Path(os.environ.get("LEDGER_DATA_ROOT", str(commons_root / "data" / "conversation_ledger")))
        knowledge_root = Path(
            os.environ.get(
                "LEDGER_KNOWLEDGE_ROOT",
                str(commons_root / "knowledge" / "conversation_ledger"),
            )
        )
        output_root = Path(os.environ.get("OUTPUT_ROOT", "E:/output/conversation-ledger"))

        return cls(
            commons_root=commons_root,
            data_root=data_root,
            knowledge_root=knowledge_root,
            output_root=output_root,
            collector_host=os.environ.get("COLLECTOR_HOST", "127.0.0.1"),
            collector_port=int(os.environ.get("COLLECTOR_PORT", "8765")),
            collector_token=os.environ.get("COLLECTOR_TOKEN", ""),
            allow_platforms=_split_csv(os.environ.get("ALLOW_PLATFORMS"))
            or ALLOWED_PLATFORMS,
            allow_projects=_split_csv(os.environ.get("ALLOW_PROJECTS")),
        )
