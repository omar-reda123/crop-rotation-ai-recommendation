import os
import json
import re
import pandas as pd
from config import CROPS_FILE

CROP_COLS = [
    "name_ar", "name_en", "scientific_name", "type", "season", 
    "growth_duration_days", "water_need_M3/acre_season", "water_need_m3_feddan_mid",
    "temp_opt_min_C", "temp_opt_max_C", "temp_abs_min_C", "temp_abs_max_C",
    "soil_texture_pref", "pest_disease_notes", "avoid_after", "good_precedent_for",
    "price_egp_per_ton", "price_year"
]

def _mid(v):
    if pd.isna(v):
        return None
    clean_str = re.sub(r"م\s*3|m\s*3|م³", "", str(v), flags=re.IGNORECASE)
    nums = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", clean_str)]
    return round(sum(nums) / len(nums)) if nums else None

def load_crops(path=CROPS_FILE):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Crop file not found at: {os.path.abspath(path)}")
    df = pd.read_csv(path, encoding="utf-8-sig")
    
    df["water_need_m3_feddan_mid"] = df["water_need_M3/acre_season"].map(_mid)
    
    df = df[CROP_COLS]
    
    return json.loads(df.where(df.notna(), None).to_json(orient="records", force_ascii=False))