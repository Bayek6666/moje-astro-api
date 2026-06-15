
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from flatlib.datetime import Datetime
from flatlib.geopos import Geopos
from flatlib.chart import Chart
from flatlib import const
from timezonefinder import TimezoneFinder
from datetime import datetime
import pytz

app = FastAPI()

# Povolení CORS, aby na toto API mohl sahat tvůj frontend z Lovable
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tf = TimezoneFinder()

@app.get("/calculate")
def calculate_chart(date: str, time: str, lat: float, lon: float):
    # Očekává formát date="1995-12-15" a time="09:06"
    
    # 1. Automatické zjištění časového pásma a historického posunu (DST)
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    local_tz = pytz.timezone(tz_name)
    
    naive_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    local_dt = local_tz.localize(naive_dt)
    
    # Výpočet posunu vůči UTC v hodinách
    offset_hours = local_dt.utcoffset().total_seconds() / 3600
    offset_sign = "+" if offset_hours >= 0 else "-"
    offset_str = f"{offset_sign}{abs(int(offset_hours)):02d}:00"
    
    # 2. Příprava dat pro astrologickou knihovnu Flatlib
    flatlib_date = date.replace("-", "/") # formát YYYY/MM/DD
    dob = Datetime(flatlib_date, time, offset_str)
    pos = Geopos(lat, lon)
    
    # 3. Výpočet horoskopu (Placidus)
    chart = Chart(dob, pos, hsys=const.HOUSES_PLACIDUS)
    
    # 4. Sestavení čistého JSON výstupu
    result = {"planets": {}, "houses": {}}
    
    for obj in chart.objects:
        result["planets"][obj.id] = {
            "sign": obj.sign,
            "degree": round(obj.signlon, 2), # Stupně ve znamení
            "house": chart.getHouse(obj).id if chart.getHouse(obj) else None
        }
        
    for house in chart.houses:
        result["houses"][house.id] = {
            "sign": house.sign,
            "degree": round(house.signlon, 2)
        }
        
    return result
