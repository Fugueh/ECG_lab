# ECG Lab

ECG Lab is an ECG signal processing and monitoring project organized around a single top-level Python package: `ecg_lab`.

The repository now centers on three areas:
- `ecg_lab.core`: ECG signal and HR/HRV related algorithm code
- `ecg_lab.app`: monitor UI and app-facing runtime logic
- `ecg_lab.cli`: one command-line entry point for data processing and monitor launch

## Repository Layout

```text
ecg_lab/
|-- app/
|   `-- monitor.py
|-- core/
|   |-- __init__.py
|   `-- rr_hr_hrv.py
|-- __init__.py
|-- cli.py
|-- config.py
`-- pipeline.py
```

Other important directories in the repo:
- `app/monitor/`: legacy wrapper scripts and monitor assets kept for compatibility
- `app/viewer_gui/`: older viewer utilities that are not yet folded into `ecg_lab.app`
- `machine_learning/`: preprocessing, registry, and training scripts built on top of `ecg_lab`
- `tests/`: automated tests for config, pipeline, CLI, and core HR/HRV logic

## Installation

Python `3.10+` is recommended.

Install the full working set:

```bash
pip install -e .[dev,ml,monitor]
```

If you only need the core data pipeline and CLI without the monitor UI extras:

```bash
pip install -e .
```

## Configuration

The project reads configuration from environment variables, optionally loaded from a repo-root `.env` file.

Common variables:

```bash
ECG_LAB_DATA_ROOT=/path/to/data/250hz
ECG_LAB_SERIAL_PORT=COM3
ECG_LAB_BAUD=115200
ECG_LAB_MONITOR_FS=50
ECG_LAB_TIME_WINDOW=10
```

Behavior notes:
- `ECG_LAB_DATA_ROOT` controls where processed records, chunks, and registries are written.
- If `ECG_LAB_DATA_ROOT` is not set, the code first tries the legacy path `E:/ECG_data/250hz`.
- If that legacy path does not exist, it falls back to `data/250hz` inside the repository.

## CLI Quick Start

Show all commands:

```bash
python -m ecg_lab.cli --help
```

Launch the main monitor UI:

```bash
python -m ecg_lab.cli monitor
```

Launch the mini roast monitor:

```bash
python -m ecg_lab.cli monitor --variant roast
```

Convert one CSV log to Parquet:

```bash
python -m ecg_lab.cli csv2parquet path/to/raw_record_2026-04-04_120000.csv
```

Run the data pipeline:

```bash
python -m ecg_lab.cli clean-raw --sampling-rate 250
python -m ecg_lab.cli build-chunks --fs 250 --chunk-length-s 10
python -m ecg_lab.cli update-record-registry --fs 250 --chunk-length-s 10
python -m ecg_lab.cli update-chunk-registry
```

If installed as a package, you can also use:

```bash
ecg-lab --help
```

Detailed CLI documentation lives in [docs/cli.md](docs/cli.md).

## Monitor Notes

The monitor implementation now lives in `ecg_lab.app.monitor` and is launched through the CLI or compatibility wrappers.

Current monitor variants:
- `250hz`: main realtime monitor for framed serial input
- `roast`: compact always-on-top variant with simplified status text

Legacy script entry points still exist and delegate into the package implementation:
- `app/monitor/monitor_250hz.py`
- `app/monitor/roast_monitor.py`

## Testing

Run tests with:

```bash
pytest -q
```

If your environment has Windows temp directory permission issues, point pytest temp/cache into the workspace:

```bash
pytest -q --basetemp=tmp/pytest -o cache_dir=tmp/.pytest_cache
```

## Current Status

What is already unified:
- one top-level package name: `ecg_lab`
- shared config through `ecg_lab.config`
- shared CLI through `ecg_lab.cli`
- core ECG algorithms under `ecg_lab.core`
- monitor UI under `ecg_lab.app.monitor`

What is still legacy or transitional:
- `app/viewer_gui/` is still outside `ecg_lab.app`
- some compatibility scripts remain in `app/monitor/`
- `machine_learning/` scripts still exist as standalone script entry points over shared package code

## Disclaimer

This repository is for ECG signal processing experiments, tooling, and workflow development. It is not a medical diagnosis system.
