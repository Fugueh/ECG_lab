# App Utilities

This directory contains desktop-side utilities that have not all been fully migrated into the `ecg_lab` package yet.

## Layout

```text
app/
|-- monitor/
|   |-- monitor_250hz.py
|   |-- roast_monitor.py
|   |-- csv2parquet.py
|   `-- roast.ico
`-- viewer_gui/
    |-- ecg_viewer.py
    |-- ecg_viewer_multi.py
    |-- ecg_viewer_diff.py
    `-- ecg_viewer_label.py
```

## `monitor/`

This directory is now mostly a compatibility layer.

Main points:
- `monitor_250hz.py` is a thin wrapper that launches `ecg_lab.app.monitor` with the `250hz` variant.
- `roast_monitor.py` is a thin wrapper that launches `ecg_lab.app.monitor` with the `roast` variant.
- `csv2parquet.py` still provides a standalone conversion entry point, but the recommended path is the unified CLI.
- `roast.ico` is still used by the roast monitor window.

Recommended launch commands:

```bash
python -m ecg_lab.cli monitor
python -m ecg_lab.cli monitor --variant roast
```

Legacy-compatible launch commands still work:

```bash
python app/monitor/monitor_250hz.py
python app/monitor/roast_monitor.py
```

## `viewer_gui/`

This directory contains older offline viewer tools for inspecting ECG files.

Supported use cases include:
- opening CSV or Parquet ECG files
- browsing long records with sliders or multi-window layouts
- comparing annotation or peak-detection differences

Current scripts:
- `ecg_viewer.py`: basic single-window viewer
- `ecg_viewer_multi.py`: multiple synchronized windows for long recordings
- `ecg_viewer_diff.py`: difference inspection view
- `ecg_viewer_label.py`: older labeling-oriented viewer

These viewer tools are still outside `ecg_lab.app` and should be treated as legacy utilities until they are formally migrated.

## Dependencies

GUI utilities here may require:
- `PyQt5`
- `pyqtgraph`
- `numpy`
- `pandas`
- `pyarrow`
- `pyserial`

The easiest way to get a working environment is:

```bash
pip install -e .[dev,ml,monitor]
```
