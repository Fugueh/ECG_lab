#!/bin/bash

for csv in *.csv
do
    python csv2parquet.py "$csv"
done
