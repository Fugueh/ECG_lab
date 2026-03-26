from __future__ import annotations

import argparse
import logging

from .config import get_data_paths
from .pipeline import (
    convert_csv_to_parquet,
    run_nk_raw_to_clean,
    run_raw_record_to_chunk,
    run_update_chunk_registry,
    run_update_record_registry,
)


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
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
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
