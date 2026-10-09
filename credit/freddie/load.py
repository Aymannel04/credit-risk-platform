"""Convert the Freddie Mac sample zips into raw Parquet files (everything kept as text).

Raw layer = the data exactly as received, only with column names added. Typing and cleaning
happen later (staging). The text files are streamed out of each zip to a temporary file in
data/interim/_tmp (git-ignored), converted by DuckDB, then deleted.

Usage (from the repo root):
    .venv/Scripts/python -m credit.freddie.load 2008 2012 2016 2019 2022
"""
import shutil
import sys
import zipfile
from pathlib import Path

import duckdb

from credit.freddie.layout import ORIGINATION_COLUMNS, PERFORMANCE_COLUMNS

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "freddie"
OUT_DIR = ROOT / "data" / "interim" / "raw"
TMP_DIR = ROOT / "data" / "interim" / "_tmp"


def _to_parquet(txt: Path, columns: list[str], out: Path) -> int:
    """Read a pipe-delimited file without header as text and write Parquet. Returns row count."""
    names = ", ".join(f"'{c}'" for c in columns)
    types = ", ".join(f"'{c}': 'VARCHAR'" for c in columns)
    con = duckdb.connect()
    con.execute(
        f"""
        COPY (
            SELECT * FROM read_csv(
                '{txt.as_posix()}',
                delim='|', header=false, quote='', escape='',
                names=[{names}], types={{{types}}}, null_padding=false, strict_mode=false
            )
        ) TO '{out.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    n = con.execute(f"SELECT count(*) FROM read_parquet('{out.as_posix()}')").fetchone()[0]
    con.close()
    return n


def load_year(year: int) -> dict:
    zip_path = RAW_DIR / f"sample_{year}.zip"
    if not zip_path.exists():
        raise FileNotFoundError(f"missing {zip_path}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    result = {}
    with zipfile.ZipFile(zip_path) as z:
        members = {m.filename for m in z.infolist()}
        for kind, columns in (("orig", ORIGINATION_COLUMNS), ("perf", PERFORMANCE_COLUMNS)):
            name = f"sample_{kind}_{year}.txt"
            if name not in members:  # never extract anything we did not expect
                raise ValueError(f"{zip_path.name} does not contain {name}")
            tmp = TMP_DIR / name  # fixed output path: no path from the zip is ever used
            with z.open(name) as src, open(tmp, "wb") as dst:
                shutil.copyfileobj(src, dst)
            try:
                out = OUT_DIR / f"{kind}_{year}.parquet"
                result[kind] = _to_parquet(tmp, columns, out)
            finally:
                tmp.unlink(missing_ok=True)
    return result


if __name__ == "__main__":
    years = [int(a) for a in sys.argv[1:]] or [2008, 2012, 2016, 2019, 2022]
    for y in years:
        counts = load_year(y)
        print(f"{y}: origination rows={counts['orig']:,}  performance rows={counts['perf']:,}")
