from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd
from config import START_YEAR, END_YEAR
from utils import get_json, log

def _fetch_ndvi_chunk(base, lat, lon, chunk, idx):
    try:
        res = get_json(f"{base}/subset", dict(
            latitude=lat, longitude=lon, band="250m_16_days_NDVI",
            startDate=chunk[0], endDate=chunk[-1], kmAboveBelow=1, kmLeftRight=1
        ), tries=2, timeout=(8, 25))
        chunk_rows = []
        for s in res.get("subset", []):
            vals = np.array(s["data"], dtype=float)
            vals = vals[vals > -2000] * 0.0001
            if len(vals):
                chunk_rows.append(dict(date=pd.to_datetime(s["calendar_date"]), NDVI=float(np.median(vals))))
        return chunk_rows
    except Exception as e:
        log(f"  NDVI chunk {idx} skipped: {str(e)[:100]}")
        return []

def fetch_ndvi(lat, lon):
    base = "https://modis.ornl.gov/rst/api/v1/MOD13Q1"
    dates = get_json(f"{base}/dates", dict(latitude=lat, longitude=lon), tries=2, timeout=(8, 20))["dates"]
    wanted = [d["modis_date"] for d in dates if START_YEAR <= int(d["calendar_date"][:4]) <= END_YEAR]
    chunks = [wanted[i:i + 10] for i in range(0, len(wanted), 10)]
    log(f"NDVI: fetching {len(wanted)} composites in {len(chunks)} chunks (parallel)...")

    rows = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(_fetch_ndvi_chunk, base, lat, lon, c, i + 1) for i, c in enumerate(chunks)]
        for f in as_completed(futures):
            rows.extend(f.result())

    if not rows:
        raise ValueError("All NDVI chunks timed out.")
    d = pd.DataFrame(rows)
    d["year"], d["month"] = d.date.dt.year, d.date.dt.month
    return d.groupby(["year", "month"], as_index=False)["NDVI"].mean()