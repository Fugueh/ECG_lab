from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# =============================================================================
# 1. 基础路径常量与底层解析 (Base Definitions)
# =============================================================================

# 遗留数据路径：如果环境变量未设置且此路径存在，则作为备选
LEGACY_DATA_ROOT = Path("E:/ECG_data/250hz")

def get_repo_root() -> Path:
    """获取当前代码仓库的根目录"""
    return Path(__file__).resolve().parents[1]

def _resolve_data_root() -> Path:
    """核心逻辑：按优先级（环境变量 > 遗留路径 > 默认目录）解析数据根目录"""
    env_root = os.getenv("ECG_LAB_DATA_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    if LEGACY_DATA_ROOT.exists():
        return LEGACY_DATA_ROOT
    return (get_repo_root() / "data" / "250hz").resolve()


# =============================================================================
# 2. 数据路径管理 (Data Storage Management)
# =============================================================================

@dataclass(frozen=True)
class DataPaths:
    """定义项目所有的子文件夹结构"""
    root: Path
    registry: Path
    raw_record: Path
    clean_record: Path
    raw_chunk: Path
    clean_chunk: Path

    def as_dict(self) -> dict[str, Path]:
        """方便使用getattr(paths, key)访问"""
        return {
            "registry": self.registry,
            "raw_record": self.raw_record,
            "clean_record": self.clean_record,
            "raw_chunk": self.raw_chunk,
            "clean_chunk": self.clean_chunk,
        }

    def ensure_directories(self) -> None:
        """一键创建所有缺失的物理文件夹"""
        for path in self.as_dict().values():
            path.mkdir(parents=True, exist_ok=True)

def get_data_paths() -> DataPaths:
    """工厂函数：根据解析出的 root 组装完整的 DataPaths 对象"""
    root = _resolve_data_root()
    return DataPaths(
        root=root,
        registry=root / "registry",
        raw_record=root / "records" / "raw_record",
        clean_record=root / "records" / "clean_record",
        raw_chunk=root / "chunks" / "raw_chunk",
        clean_chunk=root / "chunks" / "clean_chunk",
    )


# =============================================================================
# 3. 硬件/监测环境配置 (Monitor & Hardware Settings)
# =============================================================================

@dataclass(frozen=True)
class MonitorSettings:
    """实时监测器的参数配置"""
    fs: int
    time_window: int
    serial_port: str
    baud: int

    @property
    def window(self) -> int:
        """计算属性：当前采样率下的总数据点数"""
        return self.fs * self.time_window

def get_monitor_settings() -> MonitorSettings:
    """从环境变量读取硬件配置，提供默认值作为保底"""
    return MonitorSettings(
        fs=int(os.getenv("ECG_LAB_MONITOR_FS", "50")),
        time_window=int(os.getenv("ECG_LAB_TIME_WINDOW", "10")),
        serial_port=os.getenv("ECG_LAB_SERIAL_PORT", "COM3"),
        baud=int(os.getenv("ECG_LAB_BAUD", "115200")),
    )