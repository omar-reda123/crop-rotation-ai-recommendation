import time
import requests

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def get_json(url, params=None, tries=2, timeout=(8, 20)):
    """جلب بيانات JSON مع محاولات إعادة اتصال لحماية الـ Endpoint من التجمد."""
    for i in range(tries):
        try:
            log(f"GET {url.split('?')[0]}  (try {i + 1}/{tries})")
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log(f"  failed: {str(e)[:120]}")
            if i == tries - 1:
                raise RuntimeError(f"Request failed: {url} -> {e}")
            time.sleep(1.5 * (i + 1))