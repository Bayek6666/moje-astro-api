from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from flatlib.datetime import Datetime
from flatlib.geopos import GeoPos
from flatlib.chart import Chart
from flatlib import const
from timezonefinder import TimezoneFinder
from datetime import datetime
import pytz

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tf = TimezoneFinder()

@app.get("/")
def read_root():
    return {"status": "Astro API bezi naprosto v poradku! Pro vypocet pouzij /calculate"}

@app.get("/calculate")
def calculate_chart(date: str, time: str, lat: float, lon: float):
    # Očekává date="1995-12-15" a time="09:06"
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    if not tz_name:
        tz_name = "UTC"
        
    local_tz = pytz.timezone(tz_name)
    naive_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    local_dt = local_tz.localize(naive_dt)
    
    # Výpočet přesného časového posunu včetně minut
    offset_seconds = local_dt.utcoffset().total_seconds()
    offset_hours = abs(int(offset_seconds // 3600))
    offset_minutes = abs(int((offset_seconds % 3600) // 60))
    offset_sign = "+" if offset_seconds >= 0 else "-"
    offset_str = f"{offset_sign}{offset_hours:02d}:{offset_minutes:02d}"
    
    flatlib_date = date.replace("-", "/")
    dob = Datetime(flatlib_date, time, offset_str)
    pos = GeoPos(lat, lon)
    
    chart = Chart(dob, pos, hsys=const.HOUSES_PLACIDUS)
    
    result = {"planets": {}, "houses": {}}
    
    for obj in chart.objects:
        try:
            # Opravené zjišťování domu pro danou planetu
            h = chart.houses.getObjectHouse(obj)
            house_id = h.id if h else None
        except Exception:
            house_id = None
            
        result["planets"][obj.id] = {
            "sign": obj.sign,
            "degree": round(obj.signlon, 2),
            "house": house_id
        }
        
    for house in chart.houses:
        result["houses"][house.id] = {
            "sign": house.sign,
            "degree": round(house.signlon, 2)
        }
        
    return result
