import math
import numpy as np
import pandas as pd
from config import START_YEAR, END_YEAR
from utils import get_json,log

def hargreaves_et0(tmean, tmax, tmin, lat, month):
    j = [15, 46, 74, 105, 135, 166, 196, 227, 258, 288, 319, 349][month - 1]
    phi = math.radians(lat)
    dr = 1 + 0.033 * math.cos(2 * math.pi * j / 365)
    delta = 0.409 * math.sin(2 * math.pi * j / 365 - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta))))
    ra = (24 * 60 / math.pi) * 0.0820 * dr * (
        ws * math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(delta) * math.sin(ws))
    return 0.0023 * 0.408 * ra * (tmean + 17.8) * math.sqrt(max(tmax - tmin, 0.0))

def fetch_power(lat, lon):
    url = "https://power.larc.nasa.gov/api/temporal/monthly/point"
    params = dict(parameters="T2M,T2M_MAX,T2M_MIN,PRECTOTCORR", community="AG",
                  latitude=lat, longitude=lon, start=START_YEAR, end=END_YEAR, format="JSON")
    p = get_json(url, params, tries=3, timeout=(10, 30))["properties"]["parameter"]
    rows = []
    for key in p["T2M"]:
        y, m = int(key[:4]), int(key[4:])
        if m == 13:
            continue
        rows.append(dict(year=y, month=m, **{k: p[k][key] for k in p}))
    df = pd.DataFrame(rows).replace(-999, np.nan).sort_values(["year", "month"]).reset_index(drop=True)
    df = df.interpolate(limit_direction="both")
    df["ET0"] = [hargreaves_et0(r.T2M, r.T2M_MAX, r.T2M_MIN, lat, int(r.month)) for r in df.itertuples()]
    df["Rain_mm_day"] = df["PRECTOTCORR"]
    return df[["year", "month", "T2M", "T2M_MAX", "Rain_mm_day", "ET0"]].rename(columns={"T2M": "Avg_Temp"})

def fetch_soil(lat, lon):
    url = "https://rest.isric.org/soilgrids/v2.0/properties/query"
    params = [("lat", lat), ("lon", lon), ("value", "mean")] + \
             [("property", p) for p in ("soc", "phh2o", "clay", "sand", "silt")] + \
             [("depth", "5-15cm"), ("depth", "15-30cm")]
    try:
        data = get_json(url, params, tries=3, timeout=(15, 30))
        out = {}
        for layer in data["properties"]["layers"]:
            f = layer["unit_measure"]["d_factor"] or 1
            vals = [d["values"]["mean"] for d in layer["depths"] if d["values"]["mean"] is not None]
            if vals:
                out[layer["name"]] = round(float(np.mean(vals)) / f, 2)
        return {
            "organic_carbon_g_per_kg": out.get("soc"), 
            "pH": out.get("phh2o"),
            "clay_pct": out.get("clay"), 
            "sand_pct": out.get("sand"), 
            "silt_pct": out.get("silt"),
            "source": "SoilGrids API"
        }
    except Exception as e:
        log(f"SoilGrids failed completely. Using North Delta Alluvial Soil Default Profile.")
        # قيم افتراضية واقعية جداً لأراضي شمال الدلتا (تربة طينية غرينية)
        return {
            "organic_carbon_g_per_kg": 14.5,
            "pH": 7.8,
            "clay_pct": 52.0,
            "sand_pct": 18.0,
            "silt_pct": 30.0,
            "source": "Regional Default Fallback (North Delta)"
        }