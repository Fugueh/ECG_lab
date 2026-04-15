# Machine Learning Utilities

This directory contains preprocessing, registry, labeling, and training scripts that operate on ECG data managed by the shared `ecg_lab` package.

## Purpose

The code here is mainly for offline workflows:
- cleaning raw ECG records
- splitting records into fixed-size chunks
- maintaining registries for records and chunks
- preparing labeled datasets for training
- running experiment-oriented training scripts

It is not yet a single unified production pipeline.

## Layout

```text
machine_learning/
|-- labling/
|-- predict/
|-- preprocess/
`-- registry/
```

## Relationship to `ecg_lab`

The preferred shared logic now lives in:
- `ecg_lab.config`
- `ecg_lab.pipeline`
- `ecg_lab.core`

Several scripts in this directory are thin command wrappers around those shared modules.

## Common Workflows

### Clean raw ECG records

```bash
python machine_learning/preprocess/nk_raw2clean.py
```

Equivalent shared CLI form:

```bash
python -m ecg_lab.cli clean-raw --sampling-rate 250
```

### Split records into chunks

```bash
python machine_learning/preprocess/raw_record2chunk.py
```

Equivalent shared CLI form:

```bash
python -m ecg_lab.cli build-chunks --fs 250 --chunk-length-s 10
```

### Update record registry

```bash
python machine_learning/registry/update_record_registry.py
```

Equivalent shared CLI form:

```bash
python -m ecg_lab.cli update-record-registry --fs 250 --chunk-length-s 10
```

### Update chunk registry

```bash
python machine_learning/registry/update_chunk_registry.py
```

Equivalent shared CLI form:

```bash
python -m ecg_lab.cli update-chunk-registry
```

## Data Assumptions

Most workflows here assume the configured data root contains directories like:

```text
<data-root>/
|-- registry/
|-- records/
|   |-- raw_record/
|   `-- clean_record/
`-- chunks/
    |-- raw_chunk/
    `-- clean_chunk/
```

That root is controlled by `ECG_LAB_DATA_ROOT` through `ecg_lab.config`.

## Notes on Legacy Areas

### `labling/`

The directory name is still spelled `labling`, which is legacy. It contains older scripts for label construction and sample assembly.

### `predict/`

This area contains experiment-style model training code rather than a polished packaged training entry point.

## Recommended Usage

For day-to-day preprocessing and registry work, prefer the shared CLI documented in [../docs/cli.md](../docs/cli.md).

Use these scripts directly only when you specifically want the older workflow layout.
