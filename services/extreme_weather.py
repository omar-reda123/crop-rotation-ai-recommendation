# services/agri_warning.py
import pandas as pd
import requests
import json
from config import GEMINI_API_KEY

class SmartAgriWarningSystem:
    def __init__(self, lat: float, lon: float, ai_api_key: str, lang: str = "ar"):
        self.lat = lat
        self.lon = lon
        self.api_key = ai_api_key
        self.lang = lang

    def fetch_climate_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        url = "https://climate-api.open-meteo.com/v1/climate"
        params = {
            "latitude": self.lat,
            "longitude": self.lon,
            "start_date": start_date,
            "end_date": end_date,
            "models": "MRI_AGCM3_2_S",
            "daily": [
                "temperature_2m_max",
                "temperature_2m_min",
                "relative_humidity_2m_mean",
                "wind_speed_10m_mean",
            ],
        }

        response = requests.get(url, params=params)
        if response.status_code != 200:
            raise Exception("Failed to fetch climate data" if self.lang == "en" else "فشل في جلب البيانات المناخية من Open-Meteo")

        data = response.json()["daily"]
        return pd.DataFrame({
            "Date": pd.to_datetime(data["time"]),
            "Temp_Max_C": data["temperature_2m_max"],
            "Temp_Min_C": data["temperature_2m_min"],
            "Humidity_Pct": data["relative_humidity_2m_mean"],
            "Wind_Speed_m_s": data["wind_speed_10m_mean"],
        })

    def extract_extreme_events(self, df: pd.DataFrame, season: str) -> pd.DataFrame:
        if season in ["الصيف", "Summer"]:
            return df[(df["Temp_Max_C"] >= 38) | (df["Humidity_Pct"] >= 80) | (df["Wind_Speed_m_s"] >= 8)]
        elif season in ["الشتاء", "Winter"]:
            return df[(df["Temp_Min_C"] <= 5) | (df["Temp_Max_C"] >= 30) | (df["Humidity_Pct"] >= 85) | (df["Wind_Speed_m_s"] >= 8)]
        else:
            return df[(df["Temp_Max_C"] >= 35) | (df["Temp_Min_C"] <= 10) | (df["Wind_Speed_m_s"] >= 10)]

    def parse_advice_to_items(self, advice_text: str) -> list:
        days_blocks = [block.strip() for block in advice_text.split("---") if block.strip()]
        parsed_items = []

        for block in days_blocks:
            item = {}
            for line in block.split("\n"):
                line = line.strip().lstrip("-").strip()
                if self.lang == "ar":
                    if line.startswith("اليوم والتاريخ:"):
                        item["day_and_date"] = line.replace("اليوم والتاريخ:", "").strip()
                    elif line.startswith("المحصول المتضرر:"):
                        item["affected_crops"] = line.replace("المحصول المتضرر:", "").strip()
                    elif line.startswith("نوع الضرر:"):
                        item["damage_type"] = line.replace("نوع الضرر:", "").strip()
                    elif line.startswith("إجراءات الحماية:"):
                        item["protection_measures"] = line.replace("إجراءات الحماية:", "").strip()
                else:
                    if line.startswith("Day and Date:"):
                        item["day_and_date"] = line.replace("Day and Date:", "").strip()
                    elif line.startswith("Affected Crop:") or line.startswith("Affected Crops:"):
                        item["affected_crops"] = line.replace("Affected Crop:", "").replace("Affected Crops:", "").strip()
                    elif line.startswith("Damage Type:"):
                        item["damage_type"] = line.replace("Damage Type:", "").strip()
                    elif line.startswith("Protection Measures:"):
                        item["protection_measures"] = line.replace("Protection Measures:", "").strip()
            if item:
                parsed_items.append(item)

        return parsed_items

    def get_ai_advice(self, crops_str: str, extreme_df: pd.DataFrame) -> dict:
        if extreme_df.empty:
            return {
                "status": "safe",
                "alerts_count": 0,
                "advice": [],
            }

        alerts_text = ""
        for _, row in extreme_df.iterrows():
            date_str = row["Date"].strftime("%Y-%m-%d")
            conditions = []
            if self.lang == "ar":
                if row["Temp_Max_C"] >= 38:
                    conditions.append(f"حرارة عظمى ({row['Temp_Max_C']}°C)")
                if row["Temp_Min_C"] <= 5:
                    conditions.append(f"صقيع ({row['Temp_Min_C']}°C)")
                if row["Humidity_Pct"] >= 85:
                    conditions.append(f"رطوبة عالية ({row['Humidity_Pct']}%)")
                if row["Wind_Speed_m_s"] >= 8:
                    conditions.append(f"رياح قوية ({row['Wind_Speed_m_s']} م/ث)")
                if conditions:
                    alerts_text += f"التاريخ: {date_str} | الظروف المتوقعة: {', '.join(conditions)}\n"
            else:
                if row["Temp_Max_C"] >= 38:
                    conditions.append(f"Max Temp ({row['Temp_Max_C']}°C)")
                if row["Temp_Min_C"] <= 5:
                    conditions.append(f"Frost ({row['Temp_Min_C']}°C)")
                if row["Humidity_Pct"] >= 85:
                    conditions.append(f"High Humidity ({row['Humidity_Pct']}%)")
                if row["Wind_Speed_m_s"] >= 8:
                    conditions.append(f"Strong Wind ({row['Wind_Speed_m_s']} m/s)")
                if conditions:
                    alerts_text += f"Date: {date_str} | Conditions: {', '.join(conditions)}\n"

        if self.lang == "en":
            prompt = f"""
You are an automated agricultural early warning system. IMPORTANT: You MUST respond STRICTLY in English. Do not write any Arabic words, introductions, or conclusions.
Based on the following climate alerts for crops: {crops_str}

Alerts:
{alerts_text}

Extract data and respond in the following exact format for each extreme day, separating days with ---:
- Day and Date: [Write date here]
- Affected Crop: [Crop name]
- Damage Type: [Very concise scientific explanation in English]
- Protection Measures: [Direct practical steps in English]
"""
        else:
            prompt = f"""
أنت نظام آلي للإنذار الزراعي. لا تستخدم أي مقدمات مثل "أنا كمهندس" أو خاتمات. لا تستخدم كلمات مثل "الروشتة".
بناءً على التنبيهات المناخية التالية للمحاصيل: {crops_str}

التنبيهات:
{alerts_text}

استخرج البيانات وقم بالرد بالشكل التالي لكل يوم متطرف، وافصل بين الأيام بخط ---:
- اليوم والتاريخ: [اكتب التاريخ هنا]

- المحصول المتضرر: [اسم المحصول من القائمة]

- نوع الضرر: [شرح علمي مختصر جداً للضرر المباشر]

- إجراءات الحماية: [خطوات عملية مباشرة يجب على المزارع فعلها]
"""

        # استخدام موديل gemini-3.5-flash الحديث
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}

        response = requests.post(url, headers=headers, data=json.dumps(payload))

        if response.status_code == 200:
            ai_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            structured_advice = self.parse_advice_to_items(ai_text)
            return {
                "status": "alert",
                "alerts_count": len(structured_advice),
                "advice": structured_advice,
            }
        else:
            raise Exception(f"Gemini Server Error: {response.text}")


def determine_season(month: int, lang: str = "ar") -> str:
    if month in [12, 1, 2]:
        return "Winter" if lang == "en" else "الشتاء"
    elif month in [3, 4, 5]:
        return "Spring" if lang == "en" else "الربيع"
    elif month in [6, 7, 8]:
        return "Summer" if lang == "en" else "الصيف"
    return "Autumn" if lang == "en" else "الخريف"