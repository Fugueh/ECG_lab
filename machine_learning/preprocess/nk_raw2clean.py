import argparse
import logging

from ecg_lab.config import get_data_paths
from ecg_lab.pipeline import run_nk_raw_to_clean


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean raw ECG records with NeuroKit")
    parser.add_argument("--sampling-rate", type=int, default=250, help="Sampling rate used for NeuroKit processing")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    run_nk_raw_to_clean(get_data_paths(), sampling_rate=args.sampling_rate)


if __name__ == "__main__":
    main()
