# CLI Guide

This document describes the command-line interface exposed by `ecg_lab.cli`.

## Entry Points

You can use either form:

```bash
python -m ecg_lab.cli --help
```

or, after installation:

```bash
ecg-lab --help
```

Global option:
- `--log-level`: logging verbosity, for example `INFO` or `DEBUG`

Example:

```bash
python -m ecg_lab.cli --log-level DEBUG update-chunk-registry
```

## Command Overview

Available subcommands:
- `monitor`
- `csv2parquet`
- `clean-raw`
- `build-chunks`
- `update-record-registry`
- `update-chunk-registry`

## `monitor`

Launch the realtime monitor UI.

Usage:

```bash
python -m ecg_lab.cli monitor
python -m ecg_lab.cli monitor --variant roast
```

Options:
- `--variant {250hz,roast}`: choose which monitor UI to launch

Variants:
- `250hz`: main monitor window for the framed serial input workflow
- `roast`: smaller always-on-top monitor with compact status text

Related environment variables:
- `ECG_LAB_SERIAL_PORT`
- `ECG_LAB_BAUD`
- `ECG_LAB_MONITOR_FS`
- `ECG_LAB_TIME_WINDOW`

Notes:
- The monitor loads `.env` from the repository root if present.
- Logs are written as `raw_record_YYYY-MM-DD_HHMMSS.csv` in the current working directory.
- The monitor depends on the optional `monitor` extras: `pyqt5`, `pyqtgraph`, `pyserial`, and `python-dotenv`.

## `csv2parquet`

Convert a single monitor CSV log into a Parquet file next to it.

Usage:

```bash
python -m ecg_lab.cli csv2parquet path/to/raw_record_2026-04-04_120000.csv
```

Arguments:
- `csv_file`: path to the input CSV file

Behavior:
- Reads the CSV with pandas
- Writes a `.parquet` file with the same base name
- Uses `pyarrow` through the shared pipeline layer

## `clean-raw`

Run NeuroKit cleaning over raw ECG records.

Usage:

```bash
python -m ecg_lab.cli clean-raw --sampling-rate 250
```

Options:
- `--sampling-rate`: sampling rate passed to NeuroKit, default `250`

Behavior:
- Reads raw record Parquet files from the configured data root
- Writes cleaned records into the clean record directory
- Updates the ECG info output under the registry directory

Dependencies:
- Requires optional `ml` dependencies, especially `neurokit2`

## `build-chunks`

Split raw records into fixed-length chunks.

Usage:

```bash
python -m ecg_lab.cli build-chunks --fs 250 --chunk-length-s 10
```

Options:
- `--fs`: sampling rate, default `250`
- `--chunk-length-s`: chunk duration in seconds, default `10`

Behavior:
- Scans raw record Parquet files
- Splits them into exact fixed-length windows
- Drops incomplete tail chunks
- Writes raw chunk Parquet files
- Updates `chunk_registry.csv`

## `update-record-registry`

Refresh the record-level registry for saved records.

Usage:

```bash
python -m ecg_lab.cli update-record-registry --fs 250 --chunk-length-s 10
```

Options:
- `--fs`: sampling rate, default `250`
- `--chunk-length-s`: chunk duration in seconds, default `10`

Behavior:
- Scans raw records under the configured data root
- Calculates metadata such as duration, sample count, full chunk count, and tail information
- Updates `record_registry.csv`

## `update-chunk-registry`

Rebuild the chunk registry from saved chunk files.

Usage:

```bash
python -m ecg_lab.cli update-chunk-registry
```

Behavior:
- Reads saved raw chunk Parquet files
- Rebuilds a consolidated `chunk_registry.csv`

## Data Root Layout

Most non-monitor CLI commands work under `ECG_LAB_DATA_ROOT`.

The package expects a structure like:

```text
<data-root>/
©À©¤©¤ registry/
©À©¤©¤ records/
©¦   ©À©¤©¤ raw_record/
©¦   ©¸©¤©¤ clean_record/
©¸©¤©¤ chunks/
    ©À©¤©¤ raw_chunk/
    ©¸©¤©¤ clean_chunk/
```

If the directories do not exist yet, the package creates them when needed.

## Typical Workflows

### Capture and convert one recording

```bash
python -m ecg_lab.cli monitor
python -m ecg_lab.cli csv2parquet raw_record_2026-04-04_120000.csv
```

### Prepare records for downstream ML

```bash
python -m ecg_lab.cli clean-raw --sampling-rate 250
python -m ecg_lab.cli build-chunks --fs 250 --chunk-length-s 10
python -m ecg_lab.cli update-record-registry --fs 250 --chunk-length-s 10
python -m ecg_lab.cli update-chunk-registry
```

## Troubleshooting

### Import or dependency errors

If a command fails due to a missing package, install the corresponding extras:

```bash
pip install -e .[monitor]
pip install -e .[ml]
pip install -e .[dev,ml,monitor]
```

### Windows pytest temp/cache permission problems

Use workspace-local pytest paths:

```bash
python -m pytest -q --basetemp=tmp/pytest -o cache_dir=tmp/.pytest_cache
```

### Monitor launches but serial open fails

Check:
- `ECG_LAB_SERIAL_PORT`
- `ECG_LAB_BAUD`
- whether the device is already occupied by another program
