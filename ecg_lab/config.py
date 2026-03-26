from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


LEGACY_DATA_ROOT = Path("E:/ECG_data/250hz")


def get_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_data_root() -> Path:
    env_root = os.getenv("ECG_LAB_DATA_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    if LEGACY_DATA_ROOT.exists():
        return LEGACY_DATA_ROOT
    return (get_repo_root() / "data" / "250hz").resolve()


@dataclass(frozen=True)
class DataPaths:
    root: Path
    registry: Path
    raw_record: Path
    clean_record: Path
    raw_chunk: Path
    clean_chunk: Path

    def as_dict(self) -> dict[str, Path]:
        return {
            "registry": self.registry,
            "raw_record": self.raw_record,
            "clean_record": self.clean_record,
            "raw_chunk": self.raw_chunk,
            "clean_chunk": self.clean_chunk,
        }

    def ensure_directories(self) -> None:
        for path in self.as_dict().values():
            path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class MonitorSettings:
    fs: int
    time_window: int
    serial_port: str
    baud: int

    @property
    def window(self) -> int:
        return self.fs * self.time_window


def get_data_paths() -> DataPaths:
    root = _resolve_data_root()
    return DataPaths(
        root=root,
        registry=root / "registry",
        raw_record=root / "records" / "raw_record",
        clean_record=root / "records" / "clean_record",
        raw_chunk=root / "chunks" / "raw_chunk",
        clean_chunk=root / "chunks" / "clean_chunk",
    )


def get_monitor_settings() -> MonitorSettings:
    return MonitorSettings(
        fs=int(os.getenv("ECG_LAB_MONITOR_FS", "50")),
        time_window=int(os.getenv("ECG_LAB_TIME_WINDOW", "10")),
        serial_port=os.getenv("ECG_LAB_SERIAL_PORT", "COM3"),
        baud=int(os.getenv("ECG_LAB_BAUD", "115200")),
    )
