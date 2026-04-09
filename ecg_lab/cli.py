from __future__ import annotations

import argparse
import logging

MONITOR_VARIANTS = ("250hz", "roast", "ecgresp")


def launch_monitor(variant: str) -> None:
    from ecg_lab.app.monitor import launch_monitor as launch_monitor_app

    launch_monitor_app(variant)


def launch_viewer(ecg_file: str, column: str = "ecg", meanhr: bool = False) -> None:
    from ecg_lab.app.viewer import launch_viewer as launch_viewer_app

    launch_viewer_app(ecg_file, column=column, meanhr=meanhr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ECG Lab command line tools")
    parser.add_argument("--log-level", default="INFO", help="Logging level, e.g. INFO or DEBUG")
    subparsers = parser.add_subparsers(dest="command", required=True)

    csv_parser = subparsers.add_parser("csv2parquet", help="Convert a CSV log file to Parquet")
    csv_parser.add_argument("csv_file")

    clean_parser = subparsers.add_parser("clean-raw", help="Clean raw ECG records with NeuroKit")
    clean_parser.add_argument("--sampling-rate", type=int, default=250)

    chunk_parser = subparsers.add_parser("build-chunks", help="Split raw records into fixed windows")
    chunk_parser.add_argument("--fs", type=int, default=250)
    chunk_parser.add_argument("--chunk-length-s", type=int, default=10)

    record_parser = subparsers.add_parser("update-record-registry", help="Refresh record registry")
    record_parser.add_argument("--fs", type=int, default=250)
    record_parser.add_argument("--chunk-length-s", type=int, default=10)

    subparsers.add_parser("update-chunk-registry", help="Refresh chunk registry from saved chunks")

    monitor_parser = subparsers.add_parser("monitor", help="Launch the realtime monitor UI")
    monitor_parser.add_argument(
        "--variant",
        choices=sorted(MONITOR_VARIANTS),
        default="250hz",
        help="Monitor variant to launch",
    )

    viewer_parser = subparsers.add_parser("viewer", help="Launch the offline ECG viewer UI")
    viewer_parser.add_argument(
        "ecg_file",
        help="ECG CSV or Parquet file to open",
    )
    viewer_parser.add_argument(
        "--column",
        default="ecg",
        help="ECG data column to plot (default: ecg)",
    )
    viewer_parser.add_argument(
        "--meanhr",
        action="store_true",
        help="Show mean heart rate in the detail panel",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")

    if args.command == "monitor":
        launch_monitor(args.variant)
        return

    if args.command == "viewer":
        launch_viewer(args.ecg_file, column=args.column, meanhr=args.meanhr)
        return

    from .config import get_data_paths
    from .pipeline import (
        convert_csv_to_parquet,
        run_nk_raw_to_clean,
        run_raw_record_to_chunk,
        run_update_chunk_registry,
        run_update_record_registry,
    )

    paths = get_data_paths()

    if args.command == "csv2parquet":
        convert_csv_to_parquet(args.csv_file)
    elif args.command == "clean-raw":
        run_nk_raw_to_clean(paths, sampling_rate=args.sampling_rate)
    elif args.command == "build-chunks":
        run_raw_record_to_chunk(paths, fs=args.fs, chunk_length_s=args.chunk_length_s)
    elif args.command == "update-record-registry":
        run_update_record_registry(paths, fs=args.fs, chunk_length_s=args.chunk_length_s)
    elif args.command == "update-chunk-registry":
        run_update_chunk_registry(paths)
    else:
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
