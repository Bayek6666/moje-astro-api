from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from timezonefinder import TimezoneFinder
from datetime import datetime
import pytz
import swisseph as swe

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tf = TimezoneFinder()

# České názvy znamení zvěrokruhu
ZODIAC_SIGNS_CZ = [
    "Beran", "Býk", "Blíženci", "Rak", "Lev", "Panna",
    "Váhy", "Štír", "Střelec", "Kozoroh", "Vodnář", "Ryby"
]

# Seznam hlavních planet pro filtraci planetárních aspektů
PLANETS_LIST = ["Slunce", "Měsíc", "Merkur", "Venuše", "Mars", "Jupiter", "Saturn", "Uran", "Neptun", "Pluto"]

def get_sign_and_deg_str(lon):
    sign_idx = int(lon // 30)
    deg_pure = lon % 30
    deg = int(deg_pure)
    minute = int(round((deg_pure - deg) * 60))
    if minute == 60:
        deg += 1
        minute = 0
        if deg >= 30:
            deg = 0
            sign_idx = (sign_idx + 1) % 12
    return ZODIAC_SIGNS_CZ[sign_idx], f"{deg}°{minute:02d}'"

def get_angle_diff(lon1, lon2):
    diff = abs(lon1 - lon2) % 360
    if diff > 180:
        diff = 360 - diff
    return diff

def find_house_idx(lon, cusps):
    for i in range(1, 12):
        c1 = cusps[i]
        c2 = cusps[i+1]
        if c2 < c1:  # Přechod přes 0° Berana (360°)
            if lon >= c1 or lon < c2: return i
        else:
            if c1 <= lon < c2: return i
    return 12

def compute_data_at_jd(jd_ut, lat, lon):
    # Výpočet domů (Placidus = b'P')
    cusps, ascmc = swe.houses(jd_ut, lat, lon, b'P')
    asc = ascmc[0]
    mc = ascmc[1]
    vertex = ascmc[3]
    
    # Výpočet pozic těles
    sun = swe.calc_ut(jd_ut, swe.SUN)[0]
    moon = swe.calc_ut(jd_ut, swe.MOON)[0]
    mercury = swe.calc_ut(jd_ut, swe.MERCURY)[0]
    venus = swe.calc_ut(jd_ut, swe.VENUS)[0]
    mars = swe.calc_ut(jd_ut, swe.MARS)[0]
    jupiter = swe.calc_ut(jd_ut, swe.JUPITER)[0]
    saturn = swe.calc_ut(jd_ut, swe.SATURN)[0]
    uranus = swe.calc_ut(jd_ut, swe.URANUS)[0]
    neptune = swe.calc_ut(jd_ut, swe.NEPTUNE)[0]
    pluto = swe.calc_ut(jd_ut, swe.PLUTO)[0]
    node = swe.calc_ut(jd_ut, swe.TRUE_NODE)[0]  # Pravý vzestupný uzel
    lilith = swe.calc_ut(jd_ut, swe.MEAN_APOGEE)[0]  # Černá Luna (Lilith)
    chiron = swe.calc_ut(jd_ut, swe.CHIRON)[0]
    
    # Výpočet Bodu Štěstí (Pars Fortunae) podle denního/nočního zrození
    sun_house = find_house_idx(sun[0], cusps)
    is_day = sun_house >= 7
    if is_day:
        fortune_lon = (asc + moon[0] - sun[0]) % 360
    else:
        fortune_lon = (asc + sun[0] - moon[0]) % 360
        
    elements = {
        "Slunce": (sun[0], sun[3], "planeta"),
        "Měsíc": (moon[0], moon[3], "planeta"),
        "Merkur": (mercury[0], mercury[3], "planeta"),
        "Venuše": (venus[0], venus[3], "planeta"),
        "Mars": (mars[0], mars[3], "planeta"),
        "Jupiter": (jupiter[0], jupiter[3], "planeta"),
        "Saturn": (saturn[0], saturn[3], "planeta"),
        "Uran": (uranus[0], uranus[3], "planeta"),
        "Neptun": (neptune[0], neptune[3], "planeta"),
        "Pluto": (pluto[0], pluto[3], "planeta"),
        "Severní Uzel": (node[0], node[3], "bod"),
        "Lilith": (lilith[0], lilith[3], "bod"),
        "Chirón": (chiron[0], chiron[3], "bod"),
        "Bod Štěstí": (fortune_lon, 0, "bod"),
        "Vertex": (vertex, 0, "bod"),
        "Ascendent": (asc, 0, "osa"),
        "MC": (mc, 0, "osa")
    }
    return elements, cusps

@app.get("/")
def read_root():
    return {"status": "Astro API bezi naprosto v poradku! Pro vypocet pouzij /calculate"}

@app.get("/calculate")
def calculate_chart(date: str, time: str, lat: float, lon: float):
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    if not tz_name:
        tz_name = "UTC"
        
    local_tz = pytz.timezone(tz_name)
    naive_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    local_dt = local_tz.localize(naive_dt)
    utc_dt = local_dt.astimezone(pytz.utc)
    
    hour_decimal = utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0
    jd_ut = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, hour_decimal)
    
    # Spočítat aktuální data a data o kousek v budoucnosti pro detekci Aplikující/Separující
    elements, cusps = compute_data_at_jd(jd_ut, lat, lon)
    elements_future, _ = compute_data_at_jd(jd_ut + 0.005, lat, lon)
    
    postaveni = {}
    for name, (e_lon, e_speed, e_type) in elements.items():
        znameni, stupne = get_sign_and_deg_str(e_lon)
        item = {"znameni": znameni, "stupne": stupne}
        
        if name not in ["Ascendent", "MC"]:
            dum_idx = find_house_idx(e_lon, cusps)
            item["dum"] = f"{dum_idx}. dům"
            
        if name in ["Slunce", "Měsíc", "Merkur", "Venuše", "Mars", "Jupiter", "Saturn", "Uran", "Neptun", "Pluto", "Severní Uzel"]:
            item["retrográdní"] = "Ano" if e_speed < 0 else "Ne"
            
        postaveni[name] = item
        
    domy = {}
    for i in range(1, 13):
        znameni, stupne = get_sign_and_deg_str(cusps[i])
        domy[f"{i}. dům"] = {"znameni": znameni, "stupne": stupne}
        
    # Aspekty (Konjunkce, Opozice, Trigon, Kvadratura, Sextil) s orbem max 8°
    ASPECT_TYPES = [
        {"jmeno": "Konjunkce", "uhel": 0, "orb": 8.0},
        {"jmeno": "Opozice", "uhel": 180, "orb": 8.0},
        {"jmeno": "Trigon", "uhel": 120, "orb": 8.0},
        {"jmeno": "Kvadratura", "uhel": 90, "orb": 8.0},
        {"jmeno": "Sextil", "uhel": 60, "orb": 8.0}
    ]
    
    planet_aspects = []
    other_aspects = []
    all_keys = list(elements.keys())
    
    for i in range(len(all_keys)):
        for j in range(i + 1, len(all_keys)):
            p1 = all_keys[i]
            p2 = all_keys[j]
            
            lon1, _, _ = elements[p1]
            lon2, _, _ = elements[p2]
            
            diff = get_angle_diff(lon1, lon2)
            
            for asp in ASPECT_TYPES:
                current_orb = abs(diff - asp["uhel"])
                if current_orb <= asp["orb"]:
                    # Zjistit pohyb orbu pro určení fáze
                    lon1_f, _, _ = elements_future[p1]
                    lon2_f, _, _ = elements_future[p2]
                    diff_f = get_angle_diff(lon1_f, lon2_f)
                    future_orb = abs(diff_f - asp["uhel"])
                    
                    stav = "Aplikující" if future_orb < current_orb else "Separující"
                    
                    orb_deg = int(current_orb)
                    orb_min = int(round((current_orb - orb_deg) * 60))
                    if orb_min == 60:
                        orb_deg += 1
                        orb_min = 0
                    orb_str = f"{orb_deg}°{orb_min:02d}'"
                    
                    aspect_data = {
                        "vztah": f"{p1} - {p2}",
                        "typ": asp["jmeno"],
                        "orb": orb_str,
                        "stav": stav
                    }
                    
                    if p1 in PLANETS_LIST and p2 in PLANETS_LIST:
                        planet_aspects.append(aspect_data)
                    else:
                        other_aspects.append(aspect_data)
                        
    return {
        "postaveni": postaveni,
        "domy": domy,
        "aspekty_planet": planet_aspects,
        "ostatni_aspekty": other_aspects
    }
