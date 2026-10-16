# Data lake parity: the same SQL on local DuckDB and on Athena over S3

6 of 6 queries gave the same answer in both. Lake: 20 Parquet files, 261.7 MB in total.

| Query | Same answer | Rows | Athena scanned | Athena engine time |
|---|---|---|---|---|
| `dev_split_counts` | yes | 6 | 0.04 MB | 491 ms |
| `dev_vintage_sums` | yes | 6 | 0.66 MB | 528 ms |
| `fresh_structure` | yes | 4 | 0.85 MB | 762 ms |
| `raw_orig_loans` | yes | 1 | 1.57 MB | 681 ms |
| `raw_perf_rows` | yes | 1 | 0.00 MB | 644 ms |
| `raw_perf_loans` | yes | 1 | 2.69 MB | 1418 ms |

Bytes scanned is what Athena bills (about 5 USD per TB, to confirm for the region in the console). Floats are compared with a tolerance of 1e-9 (relative) / 1e-6 (absolute); counts and sums must be identical.

