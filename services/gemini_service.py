import os
import json
import time
import numpy as np
import pandas as pd
from typing import Optional
from config import START_YEAR, END_YEAR, SYSTEM, SCHEMA
from utils import log
from services.nasa_soil import fetch_power, fetch_soil
from services.modis import fetch_ndvi
from services.crops import load_crops

TARGET_MODEL = "gemini-3.5-flash"

def calculate_yearly_slope(df, column_name):
    y = df[column_name] - df.groupby("month")[column_name].transform("mean")
    x = np.arange(len(df))
    monthly_slope, _ = np.polyfit(x, y.values, 1)
    return round(float(monthly_slope * 12), 3)

def build_site_summary(lat, lon, ece=None):
    log("1/3 NASA POWER ...")
    df = fetch_power(lat, lon)
    log("2/3 MODIS NDVI ...")
    try:
        ndvi_df = fetch_ndvi(lat, lon)
        df = df.merge(ndvi_df, on=["year", "month"], how="left")
    except Exception as e:
        log(f"  NDVI skipped: {str(e)[:150]}")
    log("3/3 SoilGrids ...")
    try:
        soil = fetch_soil(lat, lon)
    except Exception as e:
        log(f"  SoilGrids skipped (server down/slow): {str(e)[:150]}")
        soil = "unavailable"

    df = df.interpolate(limit_direction="both")
    cols = [c for c in ("Avg_Temp", "Rain_mm_day", "ET0", "NDVI") if c in df and df[c].notna().any()]
    clim = df.groupby("month", as_index=False)[cols].mean().round(2)
    out = {
        "location": {"lat": lat, "lon": lon, "period": f"{START_YEAR}-{END_YEAR}"},
        "yearly_trends_5y": {c: calculate_yearly_slope(df, c) for c in cols},
        "monthly_climatology": clim.to_dict("records"),
        "soil": soil,
        "soil_salinity_ECe_dS_m": ece if ece is not None else "unknown (no data source)",
    }
    if "NDVI" in cols:
        out["low_ndvi_months(<0.25)"] = [int(m) for m in clim.loc[clim["NDVI"] < 0.25, "month"]]
    else:
        out["note"] = "NDVI unavailable: fallow periods could not be estimated"
    return out

def ask_llm(site, crops, lang="ar"):
    from google import genai
    from google.genai import types
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set!")

    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=90_000))
    
    language_instruction = (
        "Write all explanations, reasons, benefits, risks, comparisons, and reminders in simple Egyptian-friendly Arabic."
        if lang == "ar"
        else "Write all explanations, reasons, benefits, risks, comparisons, and reminders in professional English."
    )
    
    prompt = (
        f"LANGUAGE INSTRUCTION: {language_instruction}\n\n"
        f"SITE DATA:\n{json.dumps(site, ensure_ascii=False)}\n\n"
        f"CROPS TABLE:\n{json.dumps(crops, ensure_ascii=False)}\n\n"
        f"Return JSON in this schema:\n{SCHEMA}"
    )
              
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM, 
        response_mime_type="application/json",
        temperature=0.5  # الحفاظ على درجة الحرارة لتنوع الصياغة
    )

    log(f"Asking Gemini model: {TARGET_MODEL} [lang: {lang}] ...")
    
    last_err = None
    for attempt in range(2):
        try:
            resp = client.models.generate_content(
                model=TARGET_MODEL, 
                contents=prompt, 
                config=cfg
            )
            if resp is not None and getattr(resp, "text", None):
                text = resp.text.strip().removeprefix("```json").removesuffix("```").strip()
                result = json.loads(text)
                
                valid = {c["name_en"] for c in crops}
                for r in result.get("rotations", []):
                    for k in ("winter_crop", "summer_crop"):
                        if r.get(k) not in valid:
                            r.setdefault("warnings", []).append(f"{k} '{r.get(k)}' not in crops table")
                            
                result["_model"] = TARGET_MODEL
                return result
        except Exception as e:
            last_err = e
            log(f"  Gemini error ({TARGET_MODEL}) attempt {attempt + 1}: {str(e)[:180]}")
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(15 * (attempt + 1))
                continue
            break
            
    raise RuntimeError(f"Gemini model {TARGET_MODEL} failed. Last error: {last_err}")
def generate_full_recommendation(lat: float, lon: float, ece: Optional[float] = None, lang: str = "ar", save_to_file: bool = True):
    crops = load_crops()
    site = build_site_summary(lat, lon, ece=ece)
    
    llm_result = ask_llm(site, crops, lang=lang)

    full_response = {
        "status": "success",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "language": lang, 
        "site_summary": site,
        "recommendation": llm_result
    }

    if save_to_file:
        from config import OUTPUT_JSON_FILE
        with open(OUTPUT_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(full_response, f, ensure_ascii=False, indent=2)
        log(f"Saved full JSON output to {OUTPUT_JSON_FILE}")

    return full_response