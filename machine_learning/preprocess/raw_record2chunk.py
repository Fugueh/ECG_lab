import argparse
import logging

from ecg_lab.config import get_data_paths
from ecg_lab.pipeline import run_raw_record_to_chunk


def main() -> None:
    parser = argparse.ArgumentParser(description="Split raw ECG records into fixed-length chunks")
    parser.add_argument("--fs", type=int, default=250, help="Sampling rate of the raw ECG records")
    parser.add_argument("--chunk-length-s", type=int, default=10, help="Chunk length in seconds")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    run_raw_record_to_chunk(get_data_paths(), fs=args.fs, chunk_length_s=args.chunk_length_s)


if __name__ == "__main__":
    main()
