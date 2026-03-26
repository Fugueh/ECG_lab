import argparse
import logging

from ecg_lab.pipeline import convert_csv_to_parquet


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert ECG monitor CSV logs to Parquet")
    parser.add_argument("csv_file", help="Input CSV file")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")
    convert_csv_to_parquet(args.csv_file)


if __name__ == "__main__":
    main()
