import sys
from enum import Enum
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import GEMINI_API_KEY
from services.gemini_service import generate_full_recommendation
from services.extreme_weather import SmartAgriWarningSystem, determine_season

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

app = FastAPI(title="Crop Rotation & Smart Agri API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class LanguageEnum(str, Enum):
    ar = "ar"
    en = "en"

class RotationRequest(BaseModel):
    lat: float
    lon: float
    ece: Optional[float] = None
    lang: LanguageEnum = LanguageEnum.ar


@app.get("/api/v1/recommend")
def recommend_get(
    lat: float = Query(..., ge=30.3, le=31.7, description="خط العرض لشمال الدلتا (مقبول بين 30.3 و 31.7)"),
    lon: float = Query(..., ge=29.8, le=32.3, description="خط الطول لشمال الدلتا (مقبول بين 29.8 و 32.3)"),
    ece: Optional[float] = Query(None),
    lang: LanguageEnum = Query(LanguageEnum.ar, description="لغة المخرجات المطلوبة: ar أو en فقط")
):
    try:
        return generate_full_recommendation(lat=lat, lon=lon, ece=ece, lang=lang.value)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/agri-warning")
def get_agri_warning(
    lat: float = Query(..., description="خط العرض (Latitude) مثل 30.5503"),
    lon: float = Query(..., description="خط الطول (Longitude) مثل 31.0106"),
    crops: List[str] = Query(..., description="قائمة المحاصيل المزروعة حالياً"),
    lang: LanguageEnum = Query(LanguageEnum.ar, description="لغة المخرجات المطلوبة: ar أو en فقط")
):
    try:
        processed_crops = []
        for crop in crops:
            processed_crops.extend([c.strip() for c in crop.split(",") if c.strip()])
        crops_str = "، ".join(processed_crops)

        today = datetime.today()
        start_date = today.strftime("%Y-%m-%d")
        end_date = (today + timedelta(days=30)).strftime("%Y-%m-%d")
        current_season = determine_season(today.month, lang.value)

        agri_system = SmartAgriWarningSystem(lat, lon, GEMINI_API_KEY, lang.value)
        climate_df = agri_system.fetch_climate_data(start_date, end_date)
        extreme_events_df = agri_system.extract_extreme_events(climate_df, current_season)
        result = agri_system.get_ai_advice(crops_str, extreme_events_df)

        return {
            "location": {"latitude": lat, "longitude": lon},
            "season": current_season,
            "period": {"from": start_date, "to": end_date},
            "crops": processed_crops,
            "result": result,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))