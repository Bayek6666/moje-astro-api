from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from timezonefinder import TimezoneFinder
from datetime import datetime
import pytz
import swisseph as swe
import os
import urllib.request
import ssl
import json

# Nastavení pracovní složky jako výchozí pro astrologická data
CURRENT_DIR = os.getcwd()
swe.set_ephe_path(CURRENT_DIR)

# --- ROBUSTNÍ AUTOMATICKÉ STAŽENÍ ASTROLOGICKÝCH DAT ---
FILES_TO_DOWNLOAD = ["seas_18.se1", "sepl_18.se1", "semo_18.se1"]

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

for filename in FILES_TO_DOWNLOAD:
    dest_path = os.path.join(CURRENT_DIR, filename)
    if not os.path.exists(dest_path):
        # Aktualizované, 100% funkční zdroje pro stažení přes HTTPS
        possible_urls = [
            f"https://www.astro.com/ftp/swisseph/ephe/{filename}",
            f"https://raw.githubusercontent.com/chapagain/php-swiss-ephemeris/master/sweph/{filename}"
        ]
        
        downloaded = False
        for url in possible_urls:
            try:
                req = urllib.request.Request(
                    url, 
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)'}
                )
                with urllib.request.urlopen(req, context=ssl_context, timeout=15) as response, open(dest_path, 'wb') as out_file:
                    out_file.write(response.read())
                print(f"Úspěšně stažen astrologický soubor z {url}")
                downloaded = True
                break
            except Exception as e:
                print(f"Zdroj {url} selhal: {e}")
                if os.path.exists(dest_path):
                    os.remove(dest_path) # Vyčistit poškozený soubor při nedokončeném stahování
        
        if not downloaded:
            print(f"Kritické varování: Nepodařilo se stáhnout soubor {filename} z žádného zdroje!")
# --------------------------------------------------------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

tf = TimezoneFinder()

ZODIAC_SIGNS_CZ = [
    "Beran", "Býk", "Blíženci", "Rak", "Lev", "Panna",
    "Váhy", "Štír", "Střelec", "Kozoroh", "Vodnář", "Ryby"
]

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
    c = list(cusps[1:]) if len(cusps) == 13 else list(cusps)
    
    for i in range(12):
        c1 = c[i]
        c2 = c[(i + 1) % 12]
        if c2 < c1:
            if lon >= c1 or lon < c2: 
                return i + 1
        else:
            if c1 <= lon < c2: 
                return i + 1
    return 12

def compute_data_at_jd(jd_ut, lat, lon):
    try:
        cusps, ascmc = swe.houses(jd_ut, lat, lon, b'P')
        asc = ascmc[0]
        mc = ascmc[1]
        vertex = ascmc[3]
    except swe.Error:
        cusps, ascmc = swe.houses(jd_ut, lat, lon, b'E')
        asc = ascmc[0]
        mc = ascmc[1]
        vertex = ascmc[3]
    
    bodies = [
        ("Slunce", swe.SUN, "planeta"),
        ("Měsíc", swe.MOON, "planeta"),
        ("Merkur", swe.MERCURY, "planeta"),
        ("Venuše", swe.VENUS, "planeta"),
        ("Mars", swe.MARS, "planeta"),
        ("Jupiter", swe.JUPITER, "planeta"),
        ("Saturn", swe.SATURN, "planeta"),
        ("Uran", swe.URANUS, "planeta"),
        ("Neptun", swe.NEPTUNE, "planeta"),
        ("Pluto", swe.PLUTO, "planeta"),
        ("Severní Uzel", swe.MEAN_NODE, "bod"),  
        ("Lilith", swe.MEAN_APOG, "bod"),
        ("Chirón", swe.CHIRON, "bod")           
    ]
    
    elements = {}
    for name, code, e_type in bodies:
        try:
            res = swe.calc_ut(jd_ut, code)
            elements[name] = (res[0][0], res[0][3], e_type)
        except swe.Error as e:
            print(f"Poznámka: Prvek {name} byl přeskočen: {e}")
            continue
            
    if "Slunce" in elements and "Měsíc" in elements:
        sun_lon = elements["Slunce"][0]
        moon_lon = elements["Měsíc"][0]
        sun_house = find_house_idx(sun_lon, cusps)
        is_day = sun_house >= 7
        if is_day:
            fortune_lon = (asc + moon_lon - sun_lon) % 360
        else:
            fortune_lon = (asc + sun_lon - moon_lon) % 360
        elements["Bod Štěstí"] = (fortune_lon, 0, "bod")
        
    elements["Vertex"] = (vertex, 0, "bod")
    elements["Ascendent"] = (asc, 0, "osa")
    elements["MC"] = (mc, 0, "osa")
    
    return elements, cusps

@app.get("/")
def read_root():
    response_data = {"status": "Astro API bezi naprosto v poradku! Pro vypocet pouzij /calculate"}
    return Response(content=json.dumps(response_data, ensure_ascii=False), media_type="application/json; charset=utf-8")

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
    
    elements, cusps = compute_data_at_jd(jd_ut, lat, lon)
    elements_future, _ = compute_data_at_jd(jd_ut + 0.005, lat, lon)
    
    postaveni = {}
    for name, data in elements.items():
        e_lon, e_speed, e_type = data
        znameni, stupne = get_sign_and_deg_str(e_lon)
        item = {"znameni": znameni, "stupne": stupne}
        
        if name not in ["Ascendent", "MC"]:
            dum_idx = find_house_idx(e_lon, cusps)
            item["dum"] = f"{dum_idx}. dům"
            
        if name in ["Slunce", "Měsíc", "Merkur", "Venuše", "Mars", "Jupiter", "Saturn", "Uran", "Neptun", "Pluto", "Severní Uzel"]:
            item["retrográdní"] = "Ano" if e_speed < 0 else "Ne"
            
        postaveni[name] = item
        
    domy = {}
    c_list = list(cusps[1:]) if len(cusps) == 13 else list(cusps)
    for i in range(12):
        znameni, stupne = get_sign_and_deg_str(c_list[i])
        domy[f"{i+1}. dům"] = {"znameni": znameni, "stupne": stupne}
        
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
                    if p1 in elements_future and p2 in elements_future:
                        lon1_f, _, _ = elements_future[p1]
                        lon2_f, _, _ = elements_future[p2]
                        diff_f = get_angle_diff(lon1_f, lon2_f)
                        future_orb = abs(diff_f - asp["uhel"])
                        stav = "Aplikující" if future_orb < current_orb else "Separující"
                    else:
                        stav = "Neznamy"
                    
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
                        
    vysledek = {
        "postaveni": postaveni,
        "domy": domy,
        "aspekty_planet": planet_aspects,
        "ostatni_aspekty": other_aspects
    }
    
    return Response(
        content=json.dumps(vysledek, ensure_ascii=False), 
        media_type="application/json; charset=utf-8"
    )
