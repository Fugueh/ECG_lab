import argparse
import logging

from ecg_lab.config import get_data_paths
from ecg_lab.pipeline import run_update_chunk_registry


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild the ECG chunk registry from saved chunk files")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    run_update_chunk_registry(get_data_paths())


if __name__ == "__main__":
    main()
