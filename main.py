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
            spirit_lon = (asc + sun_lon - moon_lon) % 360
        else:
            fortune_lon = (asc + sun_lon - moon_lon) % 360
            spirit_lon = (asc + moon_lon - sun_lon) % 360
        elements["Bod Štěstí"] = (fortune_lon, 0, "bod")
        elements["Bod ducha"] = (spirit_lon, 0, "bod")
        
    if "Severní Uzel" in elements:
        elements["Jižní uzel"] = ((elements["Severní Uzel"][0] + 180) % 360, elements["Severní Uzel"][1], "bod")
        
    elements["Vertex"] = (vertex, 0, "bod")
    elements["Ascendent"] = (asc, 0, "osa")
    elements["MC"] = (mc, 0, "osa")
    
    return elements, cusps

@app.get("/")
def read_root():
    response_data = {"status": "Astro API bezi naprosto v poradku! Pro vypocet pouzij /calculate"}
    return Response(
        content=json.dumps(response_data, ensure_ascii=False), 
        media_type="application/json; charset=utf-8",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
    )

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
        media_type="application/json; charset=utf-8",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


# =====================================================================
#  PŘEDPOVĚĎ: témata období, nadcházející události a polohy po dnech
#  (nový endpoint /forecast — stávající /calculate se nemění)
# =====================================================================
from datetime import timedelta
from functools import lru_cache
import numpy as np

FORECAST_SLOW = [("Jupiter", swe.JUPITER, 2.0), ("Saturn", swe.SATURN, 2.0),
                 ("Uran", swe.URANUS, 1.5), ("Neptun", swe.NEPTUNE, 1.5), ("Pluto", swe.PLUTO, 1.5)]
FORECAST_FAST = [("Slunce", swe.SUN), ("Merkur", swe.MERCURY), ("Venuše", swe.VENUS), ("Mars", swe.MARS)]
FORECAST_ALL = [("Slunce", swe.SUN), ("Měsíc", swe.MOON), ("Merkur", swe.MERCURY), ("Venuše", swe.VENUS),
                ("Mars", swe.MARS), ("Jupiter", swe.JUPITER), ("Saturn", swe.SATURN), ("Uran", swe.URANUS),
                ("Neptun", swe.NEPTUNE), ("Pluto", swe.PLUTO), ("Severní Uzel", swe.MEAN_NODE)]
FORECAST_ASPECTS = [("Konjunkce", 0), ("Sextil", 60), ("Kvadratura", 90), ("Trigon", 120), ("Opozice", 180)]
NATAL_TARGETS = ["Slunce", "Měsíc", "Merkur", "Venuše", "Mars", "Jupiter", "Saturn", "Ascendent", "MC"]


def _jd_from_local(date_str, time_str, tz):
    naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    utc = tz.localize(naive).astimezone(pytz.utc)
    return swe.julday(utc.year, utc.month, utc.day, utc.hour + utc.minute / 60.0)


def _date_of_jd(jd, tz):
    y, m, d, h = swe.revjul(jd)
    hh = int(h)
    mm = int(round((h - hh) * 60))
    if mm == 60:
        hh, mm = hh + 1, 0
    base = datetime(y, m, d) + timedelta(hours=hh, minutes=mm)
    return pytz.utc.localize(base).astimezone(tz)


def _pos(jd, code):
    r = swe.calc_ut(jd, code)[0]
    return r[0], r[3]


def _signed_orb(transit_lon, natal_lon, angle):
    """Vzdálenost od přesného aspektu se znaménkem (pro hledání okamžiku přesnosti)."""
    d = (transit_lon - natal_lon) % 360
    candidates = [angle, 360 - angle] if angle not in (0, 180) else [angle]
    best = None
    for c in candidates:
        x = ((d - c + 180) % 360) - 180
        if best is None or abs(x) < abs(best):
            best = x
    return best


def _signed_orb_np(lons, natal_lon, angle):
    """Totéž co _signed_orb, ale pro celé pole poloh najednou (numpy)."""
    d = (lons - natal_lon) % 360
    x1 = ((d - angle + 180) % 360) - 180
    if angle in (0, 180):
        return x1
    x2 = ((d - (360 - angle) + 180) % 360) - 180
    return np.where(np.abs(x2) < np.abs(x1), x2, x1)


# ---------------------------------------------------------------------
#  Sdílené výpočty: pro všechny uživatele v daný den jsou stejné, proto
#  se počítají jen jednou a drží se v paměti (lru_cache). Na uživatele
#  pak zbývá jen porovnání s jeho natálními body.
# ---------------------------------------------------------------------
SCAN_DAYS = 730
STEP = 0.25


@lru_cache(maxsize=8)
def _slow_samples(day_key):
    """Denní polohy pomalých planet v okně ±2 roky (poledne UT)."""
    jds = np.arange(day_key + 0.5 - SCAN_DAYS, day_key + 0.5 + SCAN_DAYS + 0.5, 1.0)
    out = {}
    for _, code, _orb in FORECAST_SLOW:
        out[code] = np.array([swe.calc_ut(float(j), code)[0][0] for j in jds])
    return jds, out


@lru_cache(maxsize=16)
def _fast_samples(day_key, days):
    """Polohy rychlých planet po čtvrtdnech v období předpovědi."""
    jds = np.arange(day_key + 0.5, day_key + 0.5 + days + STEP, STEP)
    out = {}
    for _, code in FORECAST_FAST:
        out[code] = np.array([swe.calc_ut(float(j), code)[0][0] for j in jds])
    return jds, out


@lru_cache(maxsize=16)
def _global_events(day_key, days):
    """Vstupy do znamení, obraty, novoluní, úplňky a zatmění (bez domů a místního času)."""
    jd_start = day_key + 0.5
    jd_end = jd_start + days
    raw = []  # (jd, typ, extra, lon pro dům)

    for p_name, p_code in [(n, c) for n, c in FORECAST_ALL if n not in ("Měsíc", "Severní Uzel")]:
        jd = jd_start
        prev_lon, prev_spd = _pos(jd, p_code)
        while jd < jd_end:
            jd2 = jd + STEP
            lon2, spd2 = _pos(jd2, p_code)
            if int(prev_lon // 30) != int(lon2 // 30):
                lo, hi = jd, jd2
                for _ in range(30):
                    mid = (lo + hi) / 2
                    if int(_pos(mid, p_code)[0] // 30) == int(prev_lon // 30):
                        lo = mid
                    else:
                        hi = mid
                raw.append((hi, "vstup", {"planeta": p_name, "znameni": ZODIAC_SIGNS_CZ[int(lon2 // 30)], "retrogradni": spd2 < 0}, lon2))
            if (prev_spd < 0) != (spd2 < 0) and p_name != "Slunce":
                lo, hi = jd, jd2
                for _ in range(30):
                    mid = (lo + hi) / 2
                    if (_pos(mid, p_code)[1] < 0) == (prev_spd < 0):
                        lo = mid
                    else:
                        hi = mid
                raw.append((hi, "obrat", {"planeta": p_name, "smer": "retrográdní" if spd2 < 0 else "přímý",
                                          "znameni": get_sign_and_deg_str(lon2)[0]}, lon2))
            jd, prev_lon, prev_spd = jd2, lon2, spd2

    def elong(jd):
        return (_pos(jd, swe.MOON)[0] - _pos(jd, swe.SUN)[0]) % 360
    jd = jd_start
    prev = elong(jd)
    while jd < jd_end:
        jd2 = jd + STEP
        cur = elong(jd2)
        for target, typ in ((0, "novoluní"), (180, "úplněk")):
            a = (prev - target) % 360
            b = (cur - target) % 360
            if a > 300 and b < 60:
                lo, hi = jd, jd2
                for _ in range(40):
                    mid = (lo + hi) / 2
                    if (elong(mid) - target) % 360 > 180:
                        lo = mid
                    else:
                        hi = mid
                m_lon = _pos(hi, swe.MOON)[0]
                raw.append((hi, typ, {"znameni": get_sign_and_deg_str(m_lon)[0]}, m_lon))
        jd, prev = jd2, cur

    try:
        jd = jd_start
        while True:
            t = swe.sol_eclipse_when_glob(jd, swe.FLG_SWIEPH)[1][0]
            if t > jd_end:
                break
            s_lon = _pos(t, swe.SUN)[0]
            raw.append((t, "zatmění Slunce", {"znameni": get_sign_and_deg_str(s_lon)[0]}, s_lon))
            jd = t + 10
        jd = jd_start
        while True:
            t = swe.lun_eclipse_when(jd, swe.FLG_SWIEPH)[1][0]
            if t > jd_end:
                break
            m_lon = _pos(t, swe.MOON)[0]
            raw.append((t, "zatmění Měsíce", {"znameni": get_sign_and_deg_str(m_lon)[0]}, m_lon))
            jd = t + 10
    except Exception as e:
        print(f"Zatmění se nepodařilo spočítat: {e}")
    return tuple(raw)


@lru_cache(maxsize=64)
def _daily_positions(start, tz_name):
    """Polohy planet v místní poledne pro start−7 … start+7."""
    tz = pytz.timezone(tz_name)
    daily = []
    base = datetime.strptime(start, "%Y-%m-%d")
    for off in range(-7, 8):
        dstr = (base + timedelta(days=off)).strftime("%Y-%m-%d")
        jd = _jd_from_local(dstr, "12:00", tz)
        postaveni = {}
        for p_name, p_code in FORECAST_ALL:
            p_lon, p_spd = _pos(jd, p_code)
            znameni, stupne = get_sign_and_deg_str(p_lon)
            postaveni[p_name] = {"znameni": znameni, "stupne": stupne, "retrográdní": "Ano" if p_spd < 0 else "Ne"}
        daily.append({"datum": dstr, "postaveni": postaveni})
    return json.dumps(daily, ensure_ascii=False)


def _windows(mask):
    """Souvislé úseky True v poli: seznam (začátek, konec) indexů včetně."""
    out = []
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return out
    breaks = np.flatnonzero(np.diff(idx) > 1)
    starts = np.concatenate(([idx[0]], idx[breaks + 1]))
    ends = np.concatenate((idx[breaks], [idx[-1]]))
    return list(zip(starts.tolist(), ends.tolist()))


@app.get("/forecast")
def forecast(date: str, time: str, lat: float, lon: float, start: str = "", days: int = 60, time_known: bool = True):
    """
    date/time/lat/lon = narození. start = první den předpovědi (YYYY-MM-DD, výchozí dnes).
    Vrací:
      themes  – vlivy pomalých planet na natální body (začátek, přesnost, konec)
      events  – vstupy planet do znamení, obraty (retrográdní/přímé), novoluní a úplňky,
                zatmění a přesné aspekty rychlých planet k Slunci, Měsíci, ASC a MC
      daily   – polohy planet v poledne pro start−7 … start+7 (pro pás dní)
    """
    days = max(7, min(int(days), 180))
    tz_name = tf.timezone_at(lng=lon, lat=lat) or "UTC"
    tz = pytz.timezone(tz_name)

    jd_birth = _jd_from_local(date, time, tz)
    natal, cusps = compute_data_at_jd(jd_birth, lat, lon)
    natal_lon = {k: v[0] for k, v in natal.items()}
    targets = [t for t in NATAL_TARGETS if t in natal_lon and (time_known or t not in ("Ascendent", "MC"))]

    today_local = datetime.now(tz).strftime("%Y-%m-%d")
    start = start or today_local
    day_key = int(_jd_from_local(start, "12:00", tz) - 0.5)
    jd_start = day_key + 0.5
    jd_end = jd_start + days

    def house_of(lon_):
        return find_house_idx(lon_, cusps) if time_known else None

    def fmt(jd):
        return _date_of_jd(jd, tz).strftime("%Y-%m-%d")

    # ---------- 1) témata období (pomalé planety, okno ±2 roky) ----------
    themes = []
    s_jds, s_lons = _slow_samples(day_key)
    today_idx = SCAN_DAYS
    for p_name, p_code, orb in FORECAST_SLOW:
        lons = s_lons[p_code]
        for t_name in targets:
            n_lon = natal_lon[t_name]
            for a_name, angle in FORECAST_ASPECTS:
                so = _signed_orb_np(lons, n_lon, angle)
                windows = []
                for i0, i1 in _windows(np.abs(so) <= orb):
                    seg = so[i0:i1 + 1]
                    flips = np.flatnonzero((seg[:-1] * seg[1:] < 0) | (seg[1:] == 0)) + 1
                    windows.append({"start": float(s_jds[i0]), "end": float(s_jds[i1]), "min": float(np.abs(seg).min()),
                                    "exact": [float(s_jds[i0 + k]) for k in flips.tolist()]})
                # průchody přes retrogradaci (mezera < 120 dní) slučujeme do jednoho tématu
                merged = []
                for w in windows:
                    if merged and w["start"] - merged[-1]["end"] < 120:
                        m = merged[-1]
                        m["end"] = w["end"]
                        m["min"] = min(m["min"], w["min"])
                        m["exact"].extend(w["exact"])
                    else:
                        merged.append(dict(w))
                for w in merged:
                    if w["end"] < jd_start or w["start"] > jd_end:
                        continue
                    if not w["exact"] and w["min"] > 0.35:
                        continue  # jen dotek okraje orbu, téma nevrcholí
                    peak = w["exact"][0] if w["exact"] else (w["start"] + w["end"]) / 2
                    if jd_start < peak:
                        phase = "sílí"
                    elif w["end"] - jd_start < 21:
                        phase = "doznívá"
                    else:
                        phase = "vrcholí"
                    themes.append({
                        "planeta": p_name,
                        "natalni": t_name,
                        "aspekt": a_name,
                        "od": fmt(w["start"]),
                        "do": fmt(w["end"]),
                        "presne": [fmt(x) for x in w["exact"]],
                        "faze": phase,
                        "dum_tranzitu": house_of(float(lons[today_idx])),
                        "dum_natalni": house_of(n_lon) if t_name not in ("Ascendent", "MC") else None,
                    })
    themes.sort(key=lambda t: (t["od"]))

    # ---------- 2) události v období ----------
    events = []
    for jd, typ, extra, e_lon in _global_events(day_key, days):
        d = _date_of_jd(jd, tz)
        events.append({"datum": d.strftime("%Y-%m-%d"), "cas": d.strftime("%H:%M"), "typ": typ, **extra, "dum": house_of(e_lon)})

    # přesné aspekty rychlých planet ke Slunci, Měsíci, ASC a MC
    f_jds, f_lons = _fast_samples(day_key, days)
    key_targets = [t for t in ("Slunce", "Měsíc", "Ascendent", "MC") if t in targets]
    for p_name, p_code in FORECAST_FAST:
        lons = f_lons[p_code]
        for t_name in key_targets:
            n_lon = natal_lon[t_name]
            for a_name, angle in FORECAST_ASPECTS:
                if a_name == "Sextil":
                    continue
                so = _signed_orb_np(lons, n_lon, angle)
                hits = np.flatnonzero((so[:-1] * so[1:] < 0) & (np.abs(so[:-1]) < 5) & (np.abs(so[1:]) < 5))
                for i in hits.tolist():
                    lo, hi, plo = float(f_jds[i]), float(f_jds[i + 1]), float(so[i])
                    for _ in range(30):
                        mid = (lo + hi) / 2
                        v = _signed_orb(_pos(mid, p_code)[0], n_lon, angle)
                        if v * plo > 0:
                            lo, plo = mid, v
                        else:
                            hi = mid
                    d = _date_of_jd(hi, tz)
                    events.append({"datum": d.strftime("%Y-%m-%d"), "cas": d.strftime("%H:%M"), "typ": "aspekt",
                                   "planeta": p_name, "natalni": t_name, "aspekt": a_name})

    events.sort(key=lambda e: (e["datum"], e["cas"]))

    # ---------- 3) polohy po dnech pro pás dní (start−7 … start+7) ----------
    daily = json.loads(_daily_positions(start, tz_name))

    vysledek = {"od": start, "dni": days, "temata": themes, "udalosti": events, "dny": daily}
    return Response(
        content=json.dumps(vysledek, ensure_ascii=False),
        media_type="application/json; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# =====================================================================
#  ASTRO MAPA (astrokartografie): rovníkové souřadnice planet a hvězdný
#  čas v okamžiku narození. Čáry ASC/DSC/MC/IC si z nich spočítá aplikace.
# =====================================================================
ASTROMAP_BODIES = [("Slunce", swe.SUN), ("Měsíc", swe.MOON), ("Merkur", swe.MERCURY), ("Venuše", swe.VENUS),
                   ("Mars", swe.MARS), ("Jupiter", swe.JUPITER), ("Saturn", swe.SATURN), ("Uran", swe.URANUS),
                   ("Neptun", swe.NEPTUNE), ("Pluto", swe.PLUTO)]


@app.get("/astromap")
def astromap(date: str, time: str, lat: float, lon: float):
    """
    date/time/lat/lon = narození (místní čas v místě narození).
    Vrací hvězdný čas v Greenwichi (stupně) a pro každou planetu rektascenzi
    a deklinaci (zdánlivé, k pravému rovníku data) ve stupních.
    """
    tz_name = tf.timezone_at(lng=lon, lat=lat) or "UTC"
    tz = pytz.timezone(tz_name)
    jd = _jd_from_local(date, time, tz)
    gst = (swe.sidtime(jd) * 15.0) % 360.0
    planety = {}
    for name, code in ASTROMAP_BODIES:
        r = swe.calc_ut(jd, code, swe.FLG_SWIEPH | swe.FLG_EQUATORIAL)[0]
        planety[name] = {"ra": round(r[0], 5), "dec": round(r[1], 5)}
    vysledek = {"gst": round(gst, 5), "jd": jd, "planety": planety}
    return Response(
        content=json.dumps(vysledek, ensure_ascii=False),
        media_type="application/json; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400"},
    )
