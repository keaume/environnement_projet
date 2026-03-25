#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Scraper - Interventions d'urgence environnementale du MELCCFP (Québec)
=====================================================================
STRATÉGIE DELTA + NOMINATIM (géocodage 100% gratuit)
-----------------------------------------------------
- cache_fiches.json    → accumule TOUTES les fiches
- cache_geocode.json   → accumule TOUS les géocodages
- Nominatim (OpenStreetMap) remplace Google → 0 $
"""

import os
import time
import csv
import re
import json
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

import folium
from folium.plugins import MarkerCluster
from tqdm import tqdm
from shapely.geometry import Point, shape


# ──────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────
BASE_URL = "https://www.environnement.gouv.qc.ca/ministere/urgence_environnement"
LISTE_URL = f"{BASE_URL}/resultats_region.asp"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_EMAIL = "antoine.toenz@gmail.com"

MAX_THREADS = 10
DELAI_SCRAPE = 0.15
DELAI_NOMINATIM = 1.1  # Nominatim: max ~1 req/sec

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
print("BASE_DIR =", BASE_DIR)
OUTPUT_DIR = BASE_DIR
print("OUTPUT_DIR =", OUTPUT_DIR)

CACHE_SCRAPE = os.path.join(BASE_DIR, "cache_fiches.json")
CACHE_GEOCODE = os.path.join(BASE_DIR, "cache_geocode.json")
GEOJSON_FILE = os.path.join(BASE_DIR, "regions_quebec.geojson")
STRICT_REGION = True

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; recherche-academique/1.0)"
}

ZOOM_REGIONS = {
    "Bas-Saint-Laurent":             (48.2,  -68.5,  8),
    "Saguenay—Lac-Saint-Jean":       (48.8,  -72.0,  7),
    "Capitale-Nationale":            (46.9,  -71.3,  9),
    "Mauricie":                      (46.7,  -72.8,  8),
    "Estrie":                        (45.4,  -71.8,  9),
    "Montréal":                      (45.55, -73.7, 11),
    "Outaouais":                     (45.8,  -75.5,  8),
    "Abitibi-Témiscamingue":         (48.5,  -77.5,  7),
    "Côte-Nord":                     (50.5,  -66.5,  6),
    "Nord-du-Québec":                (53.0,  -76.0,  5),
    "Gaspésie—Îles-de-la-Madeleine": (48.5,  -65.5,  7),
    "Chaudière-Appalaches":          (46.3,  -70.8,  8),
    "Laval":                         (45.57, -73.75, 12),
    "Lanaudière":                    (46.0,  -73.5,  9),
    "Laurentides":                   (46.2,  -74.5,  8),
    "Montérégie":                    (45.4,  -73.1,  9),
    "Centre-du-Québec":              (46.0,  -72.3,  9),
}

COULEURS = {
    "incendie": "red",
    "déversement": "orange",
    "contamination": "purple",
    "accident": "blue",
    "signalement": "gray",
    "mortalité": "darkred",
    "rejet": "darkblue",
    "émission": "beige",
    "travaux": "green",
}


# ──────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────
def couleur(nom: str) -> str:
    n = (nom or "").lower()
    for k, v in COULEURS.items():
        if k in n:
            return v
    return "lightgray"


def nom_fichier(region: str) -> str:
    tbl = str.maketrans("àâäéèêëîïôùûüç", "aaaeeeeiioouuc")
    r = (region or "").lower().translate(tbl).replace("—", "-")
    r = re.sub(r"[^a-z0-9-]", "_", r)
    return f"carte_{r}.html"


def adresse_non_postale(adresse: str) -> bool:
    a = (adresse or "").lower()
    motifs = [
        "lot ", " lots ", "cadastre", "concession", "rang ", "route forestière",
        "chemin forestier", "km ", "kilomètre", "pres de ", "près de ",
        "a environ", "à environ", "intersection", "parcelle"
    ]
    return any(m in a for m in motifs)


# ──────────────────────────────────────────────────────────────────
# POLYGONES
# ──────────────────────────────────────────────────────────────────
def charger_polygones():
    print("🗺️  Chargement des polygones des régions...")
    with open(GEOJSON_FILE, encoding="utf-8") as f:
        geojson = json.load(f)
    polygones = {}
    for feat in geojson.get("features", []):
        nom = feat.get("properties", {}).get("nom")
        if nom:
            polygones[nom] = shape(feat["geometry"])
    print(f"   → {len(polygones)} polygones chargés.")
    return polygones


def point_dans_region(polygones, region, lat, lon) -> bool:
    if lat is None or lon is None:
        return False
    if region not in polygones:
        return (44.9 <= lat <= 63.0) and (-79.8 <= lon <= -57.0)
    return polygones[region].contains(Point(lon, lat))


# ──────────────────────────────────────────────────────────────────
# CACHE
# ──────────────────────────────────────────────────────────────────
def charger_cache_scrape() -> dict:
    if not os.path.exists(CACHE_SCRAPE):
        return {}
    try:
        with open(CACHE_SCRAPE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            print("   ↻ Conversion ancien format liste → dict...")
            return {item["url"]: item for item in data if item.get("url")}
        return data
    except Exception:
        return {}


def sauver_cache_scrape(cache_dict: dict):
    with open(CACHE_SCRAPE, "w", encoding="utf-8") as f:
        json.dump(cache_dict, f, ensure_ascii=False, indent=2)


def charger_cache_geocode():
    if os.path.exists(CACHE_GEOCODE):
        try:
            with open(CACHE_GEOCODE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def sauver_cache_geocode(cache: dict):
    with open(CACHE_GEOCODE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────────────────────────
# SCRAPING
# ──────────────────────────────────────────────────────────────────
def get_regions():
    print("📋 Récupération des régions...")
    resp = requests.get(LISTE_URL, headers=HEADERS, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    regions = []
    sel = soup.find("select")
    if not sel:
        print("⚠️ Impossible de trouver la liste des régions.")
        return regions

    for opt in sel.find_all("option"):
        v = (opt.get("value") or "").strip()
        nom = opt.get_text(strip=True)
        if v and v not in ("0", "") and nom:
            regions.append({"code": v, "nom": nom})

    print(f"   → {len(regions)} régions trouvées.")
    return regions


def get_urls_region(region):
    items = []
    try:
        data = {"region": region["nom"], "nb_par_page": "5000", "soumettre": "Rechercher"}
        resp = requests.post(LISTE_URL, data=data, headers=HEADERS, timeout=60)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a["href"]
            low = href.lower()
            if any(k in low for k in ("urgence.asp?dossier=", "detail", "dossier", "fiche")):
                texte = a.get_text(strip=True)
                if not texte:
                    continue

                url = href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")
                parent = a.find_parent("tr")
                date_str = ""

                if parent:
                    tds = parent.find_all("td")
                    if tds:
                        date_str = tds[0].get_text(strip=True)

                items.append({
                    "region": region["nom"],
                    "evenement_liste": texte,
                    "date_liste": date_str,
                    "url": url
                })
    except Exception as e:
        print(f"⚠️ Erreur URL {region['nom']}: {e}")

    time.sleep(DELAI_SCRAPE)
    return items


def scraper_fiche(item):
    result = {
        "region": item.get("region", ""),
        "evenement": item.get("evenement_liste", ""),
        "date": item.get("date_liste", ""),
        "no_dossier": "",
        "adresse": "",
        "municipalite": "",
        "url": item.get("url", ""),
        "lat": None,
        "lon": None,
        "precision": "",
        "geocode_query": ""
    }

    try:
        resp = requests.get(result["url"], headers=HEADERS, timeout=30)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        champs = {}
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower().rstrip(":").strip()
                val = cells[1].get_text(" ", strip=True)
                champs[label] = val

        mapping = {
            "date": ["date de signalement de l'événement", "date de signalement", "date"],
            "no_dossier": ["numéro de dossier", "numero de dossier", "dossier"],
            "adresse": ["lieu de l'événement", "lieu de l evenement", "adresse", "lieu"],
            "municipalite": ["municipalité ou territoire", "municipalite", "ville"],
        }

        for champ, cles in mapping.items():
            for cle in cles:
                if champs.get(cle):
                    result[champ] = champs[cle]
                    break

        txt = soup.get_text(" ", strip=True)

        if not result["date"]:
            m = re.search(r"Date de signalement[^:]*:\s*([^\n|]{5,40})", txt, re.I)
            if m:
                result["date"] = m.group(1).strip()

        if not result["adresse"]:
            m = re.search(r"Lieu de l.?événement\s*:\s*([^\n|]+)", txt, re.I)
            if m:
                result["adresse"] = m.group(1).strip()

        if not result["municipalite"]:
            m = re.search(r"Municipalit[eé][^:]*:\s*([^\n|]+)", txt, re.I)
            if m:
                result["municipalite"] = m.group(1).strip()

        if not result["no_dossier"]:
            m = re.search(r"(?:Numéro de dossier|Dossier)\s*:\s*(\d+)", txt, re.I)
            if m:
                result["no_dossier"] = m.group(1).strip()

    except Exception:
        pass

    time.sleep(DELAI_SCRAPE)
    return result


# ──────────────────────────────────────────────────────────────────
# NOMINATIM
# ──────────────────────────────────────────────────────────────────
def geocode_nominatim(query: str, cache: dict):
    if query in cache:
        c = cache[query]
        return c.get("lat"), c.get("lon"), c.get("display_name", "")

    try:
        headers = {"User-Agent": f"urgences-env-quebec/1.0 ({NOMINATIM_EMAIL})"}
        r = requests.get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "json",
                "limit": 1,
                "countrycodes": "ca",
            },
            headers=headers,
            timeout=15
        )
        results = r.json()
        if results:
            lat = round(float(results[0]["lat"]), 6)
            lon = round(float(results[0]["lon"]), 6)
            display = results[0].get("display_name", "")
            cache[query] = {"lat": lat, "lon": lon, "display_name": display}
            time.sleep(DELAI_NOMINATIM)
            return lat, lon, display
    except Exception:
        pass

    cache[query] = {"lat": None, "lon": None, "display_name": ""}
    time.sleep(DELAI_NOMINATIM)
    return None, None, ""


# ──────────────────────────────────────────────────────────────────
# GPS
# ──────────────────────────────────────────────────────────────────
def extraire_coords_gps(adresse):
    dms = re.search(
        r'(\d{1,3})[°º](\d{1,2})[\'′](\d{1,2}(?:[.,]\d+)?)[\"″]?\s*([NS])\s+'
        r'(\d{1,3})[°º](\d{1,2})[\'′](\d{1,2}(?:[.,]\d+)?)[\"″]?\s*([WOEoe])',
        adresse
    )
    if dms:
        lat = int(dms.group(1)) + int(dms.group(2))/60 + float(dms.group(3).replace(',', '.'))/3600
        if dms.group(4).upper() == 'S':
            lat = -lat
        lon = int(dms.group(5)) + int(dms.group(6))/60 + float(dms.group(7).replace(',', '.'))/3600
        if dms.group(8).upper() in ('W', 'O'):
            lon = -lon
        if 44 < lat < 65 and -82 < lon < -55:
            return lat, lon

    dec_letter = re.search(
        r'(\d{2,3}[.,]\d+)[°\s]*([NS])\s*(?:et|and|,|;)\s*(\d{2,3}[.,]\d+)[°\s]*([WOEoe])',
        adresse, re.I
    )
    if dec_letter:
        lat = float(dec_letter.group(1).replace(',', '.'))
        lon = float(dec_letter.group(3).replace(',', '.'))
        if dec_letter.group(2).upper() == 'S':
            lat = -lat
        if dec_letter.group(4).upper() in ('W', 'O'):
            lon = -lon
        if 44 < lat < 65 and -82 < lon < -55:
            return lat, lon

    dec_pure = re.search(
        r'(-?\d{2,3}[.,]\d{4,})\s*[;,]\s*(-?\d{2,3}[.,]\d{4,})',
        adresse
    )
    if dec_pure:
        a = float(dec_pure.group(1).replace(',', '.'))
        b = float(dec_pure.group(2).replace(',', '.'))
        if 44 < a < 65 and -82 < b < -55:
            return a, b
        if 44 < b < 65 and -82 < a < -55:
            return b, a

    geo = re.search(
        r'(\d{1,3})deg\s*(\d{1,2}[.,]\d+)[\'′]?\s*([NS])\s*[;,]\s*'
        r'(\d{1,3})deg\s*(\d{1,2}[.,]\d+)[\'′]?\s*([WOEoe])',
        adresse, re.I
    )
    if geo:
        lat = int(geo.group(1)) + float(geo.group(2).replace(',', '.')) / 60
        if geo.group(3).upper() == 'S':
            lat = -lat
        lon = int(geo.group(4)) + float(geo.group(5).replace(',', '.')) / 60
        if geo.group(6).upper() in ('W', 'O'):
            lon = -lon
        if 44 < lat < 65 and -82 < lon < -55:
            return lat, lon

    mtm = re.search(
        r'(\d{2})\s+(\d{2}[.,]\d+)\s*([NS])\s+(\d{3})\s+(\d{2}[.,]\d+)\s*([WO])',
        adresse
    )
    if mtm:
        lat = int(mtm.group(1)) + float(mtm.group(2).replace(',', '.')) / 60
        lon = int(mtm.group(4)) + float(mtm.group(5).replace(',', '.')) / 60
        if mtm.group(3).upper() == 'S':
            lat = -lat
        lon = -lon
        if 44 < lat < 65 and -82 < lon < -55:
            return lat, lon

    return None


# ──────────────────────────────────────────────────────────────────
# MUNICIPALITÉ
# ──────────────────────────────────────────────────────────────────
def simplifier_municipalite(municipalite):
    m = (municipalite or "").strip()
    if not m:
        return None

    if re.match(
        r'(TNO\b|Territoire non organisé|Réserve faunique|Réservoir|'
        r'Parc (?:national|de la|du)|MRC de\b|Entre |Près de |À environ )',
        m, re.I
    ):
        return None

    m = re.sub(
        r'^(Ville de|Municipalité de|Municipalité Régionale de Comté du?|'
        r'Municipalité|Ville|Agglomération de)\s+',
        '',
        m,
        flags=re.I
    )

    secteur = re.search(
        r'\((?:secteur|arr\.|arrondissement|Secteur|Quartier|quartier)\s+([^)]+)\)',
        m, re.I
    )
    if secteur:
        return secteur.group(1).strip() + ', Québec'

    m = re.sub(r'\s*\([^)]+\)', '', m).strip()
    m = re.sub(r',?\s+secteur\s+.*', '', m, flags=re.I).strip()
    m = m.split('\n')[0].strip()
    m = re.split(r'\s+et\s+', m)[0].strip()
    m = re.sub(r',?\s+MRC\s+.*', '', m, flags=re.I).strip()

    if not m:
        return None

    return m + ', Québec'


# ──────────────────────────────────────────────────────────────────
# GEOCODAGE PRINCIPAL
# ──────────────────────────────────────────────────────────────────
def geocoder(evenements, polygones):
    a_geocoder = [ev for ev in evenements if not ev.get("lat") or not ev.get("lon")]
    deja_ok = len(evenements) - len(a_geocoder)

    print("\n🌍 Géocodage Nominatim (gratuit)")
    print(f"   ✅ Déjà géocodés (cache) : {deja_ok}")
    print(f"   🆕 À géocoder maintenant  : {len(a_geocoder)}")

    if not a_geocoder:
        print("   → Rien à faire 🎉")
        return evenements

    cache = charger_cache_geocode()

    queries_uniques = set()
    for ev in a_geocoder:
        adr = (ev.get("adresse") or "").strip()
        muni = (ev.get("municipalite") or "").strip()
        reg = (ev.get("region") or "").strip()

        if adr and extraire_coords_gps(adr):
            continue

        muni_simple = simplifier_municipalite(muni) if muni else None

        if adr and muni and not adresse_non_postale(adr):
            queries_uniques.add(f"{adr}, {muni}, Québec, Canada")
        if adr and reg and not adresse_non_postale(adr):
            queries_uniques.add(f"{adr}, {reg}, Québec, Canada")
        if muni:
            queries_uniques.add(f"{muni}, Québec, Canada")
        if muni_simple:
            queries_uniques.add(f"{muni_simple}, Canada")

    nouvelles = [q for q in queries_uniques if q not in cache]
    print(f"   🧠 Cache géocode : {len(cache)} entrées")
    print(f"   📡 Requêtes Nominatim à envoyer : {len(nouvelles)}")
    duree = len(nouvelles) * DELAI_NOMINATIM
    print(f"   ⏱️  Durée estimée : ~{int(duree // 60)}m{int(duree % 60)}s")
    print("   💸 Coût : 0,00 $")

    ok = rejet = approx = gps_direct = 0
    erreurs = []

    for ev in tqdm(a_geocoder, desc="Géocodage"):
        adr = (ev.get("adresse") or "").strip()
        muni = (ev.get("municipalite") or "").strip()
        reg = (ev.get("region") or "").strip()

        coords = extraire_coords_gps(adr) if adr else None
        if coords:
            lat, lon = coords
            inside = point_dans_region(polygones, reg, lat, lon)
            if not STRICT_REGION or inside:
                ev["lat"] = lat
                ev["lon"] = lon
                ev["precision"] = "gps"
                ev["geocode_query"] = f"GPS extrait de: {adr}"
                ok += 1
                gps_direct += 1
                continue

        muni_simple = simplifier_municipalite(muni) if muni else None
        tentatives = []

        # Pour les adresses non postales, on ne tente PAS l'adresse exacte
        if adr and muni and not adresse_non_postale(adr):
            tentatives.append(("adresse", f"{adr}, {muni}, Québec, Canada"))
        if adr and reg and not adresse_non_postale(adr):
            tentatives.append(("adresse_region", f"{adr}, {reg}, Québec, Canada"))

        if muni:
            tentatives.append(("ville", f"{muni}, Québec, Canada"))

        if muni_simple:
            q_simple = f"{muni_simple}, Canada"
            q_ville = f"{muni}, Québec, Canada" if muni else ""
            if q_simple.lower() != q_ville.lower():
                tentatives.append(("ville_simplifiee", q_simple))

        placed = False
        for precision, q in tentatives:
            lat, lon, display = geocode_nominatim(q, cache)
            if lat is None or lon is None:
                continue

            inside = point_dans_region(polygones, reg, lat, lon)
            if STRICT_REGION and not inside:
                continue

            ev["lat"] = lat
            ev["lon"] = lon
            ev["precision"] = precision
            ev["geocode_query"] = q
            ev["geocode_formatted"] = display

            ok += 1
            if precision in ("ville", "ville_simplifiee"):
                approx += 1
            placed = True
            break

        if not placed:
            rejet += 1
            erreurs.append({
                "region": reg,
                "evenement": ev.get("evenement", ""),
                "date": ev.get("date", ""),
                "no_dossier": ev.get("no_dossier", ""),
                "adresse": adr,
                "municipalite": muni,
                "url": ev.get("url", ""),
                "raison": "Hors polygone ou échec geocode"
            })

    sauver_cache_geocode(cache)
    print(f"   → {ok} placés ({gps_direct} GPS direct, {approx} approx.), {rejet} rejetés.")

    if erreurs:
        fichier_erreurs = os.path.join(OUTPUT_DIR, "erreurs_geocode.csv")
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(fichier_erreurs, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(erreurs[0].keys()))
            w.writeheader()
            w.writerows(erreurs)
        print(f"   ⚠️ Erreurs exportées : {fichier_erreurs}")

    return evenements


# ──────────────────────────────────────────────────────────────────
# SORTIES
# ──────────────────────────────────────────────────────────────────
def sauvegarder_csv(evenements, fichier):
    champs = [
        "region", "date", "no_dossier", "evenement", "adresse", "municipalite",
        "lat", "lon", "precision", "geocode_query", "url"
    ]
    with open(fichier, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=champs, extrasaction="ignore")
        w.writeheader()
        w.writerows(evenements)
    print(f"   ✅ CSV : {fichier} ({len(evenements)} lignes)")


def generer_carte_region(region, evenements, fichier):
    geo = ZOOM_REGIONS.get(region, (46.8, -71.2, 8))
    carte = folium.Map(location=[geo[0], geo[1]], zoom_start=geo[2], tiles="CartoDB positron")
    cluster = MarkerCluster(options={"maxClusterRadius": 40, "disableClusteringAtZoom": 13}).add_to(carte)

    n = 0
    for ev in evenements:
        if not ev.get("lat") or not ev.get("lon"):
            continue

        prec = ev.get("precision", "")
        approx = prec in ("ville", "ville_simplifiee")
        badge = "<span style='color:#b03a2e;font-weight:700'>📍 Localisation approximative</span><br>" if approx else ""

        popup = f"""
        <div style="font-family:sans-serif;font-size:13px;max-width:320px">
          <b style="color:#1a5276">{ev.get('evenement','')}</b><br>
          <hr style="margin:4px 0">
          {badge}
          📅 <b>Date :</b> {ev.get('date') or 'N/D'}<br>
          📁 <b>Dossier :</b> {ev.get('no_dossier') or 'N/D'}<br>
          📍 <b>Adresse :</b> {ev.get('adresse') or 'N/D'}<br>
          🏙️ <b>Municipalité :</b> {ev.get('municipalite') or 'N/D'}<br>
          <a href="{ev.get('url','')}" target="_blank" style="color:#2980b9;font-size:12px">🔗 Fiche complète</a>
        </div>"""

        folium.Marker(
            [ev["lat"], ev["lon"]],
            popup=folium.Popup(popup, max_width=340),
            tooltip=f"{ev.get('date','')} – {ev.get('evenement','')[:60]}",
            icon=folium.Icon(color=couleur(ev.get("evenement", "")), icon="warning-sign", prefix="glyphicon"),
        ).add_to(cluster)
        n += 1

    carte.get_root().html.add_child(folium.Element("""
    <a href="index.html" style="position:fixed;top:12px;left:12px;z-index:1000;
       background:white;padding:8px 14px;border-radius:6px;text-decoration:none;
       box-shadow:0 2px 6px rgba(0,0,0,.25);font-family:sans-serif;
       font-size:13px;color:#1a3c5e">← Toutes les régions</a>"""))

    carte.get_root().html.add_child(folium.Element(f"""
    <div style="position:fixed;top:12px;left:50%;transform:translateX(-50%);
                z-index:1000;background:rgba(255,255,255,.93);padding:8px 20px;
                border-radius:6px;box-shadow:0 2px 6px rgba(0,0,0,.25);
                font-family:sans-serif;font-size:15px;font-weight:bold;color:#1a3c5e">
      🌿 {region} — {n} interventions
    </div>"""))

    carte.save(fichier)
    return n


def generer_accueil(stats_regions, fichier):
    cartes_html = ""
    for region, count, fichier_carte in sorted(stats_regions, key=lambda x: x[0]):
        cartes_html += f"""
        <a href="{fichier_carte}" class="region-card">
            <div class="region-name">{region}</div>
            <div class="region-count">{count} interventions</div>
        </a>"""

    total = sum(c for _, c, _ in stats_regions)

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Urgences environnementales – Québec</title>
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
          background:#f0f4f8; color:#1a3c5e; }}
  header {{ background:#1a3c5e; color:white; padding:30px 20px; text-align:center; }}
  header h1 {{ font-size:1.6em; margin-bottom:8px; }}
  header p {{ opacity:0.8; font-size:0.95em; }}
  .total {{ background:#2980b9; color:white; text-align:center;
            padding:10px; font-size:0.9em; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(220px,1fr));
           gap:16px; padding:30px 20px; max-width:1100px; margin:0 auto; }}
  .region-card {{ background:white; border-radius:10px; padding:20px;
                  text-decoration:none; color:inherit;
                  box-shadow:0 2px 8px rgba(0,0,0,.08);
                  transition:transform .15s, box-shadow .15s;
                  border-left:4px solid #2980b9; }}
  .region-card:hover {{ transform:translateY(-3px);
                        box-shadow:0 6px 16px rgba(0,0,0,.15); }}
  .region-name {{ font-weight:600; font-size:1em; margin-bottom:6px; }}
  .region-count {{ color:#2980b9; font-size:0.85em; }}
  footer {{ text-align:center; padding:20px; color:#888; font-size:0.8em; }}
</style>
</head>
<body>
<header>
  <h1>🌿 Interventions d'urgence environnementale</h1>
  <p>Registre du MELCCFP — Québec</p>
</header>
<div class="total">
  {total} interventions géocodées réparties dans {len(stats_regions)} régions
</div>
<div class="grid">{cartes_html}</div>
<footer>Source : MELCCFP — Urgence-Environnement</footer>
</body>
</html>"""

    with open(fichier, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"   ✅ Page d'accueil → {fichier}")


# ──────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────
def main():
    print("=" * 66)
    print(" Scraper – Urgences env. Québec  [NOMINATIM — 100% gratuit]")
    print("=" * 66)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    polygones = charger_polygones()

    cache_scrape = charger_cache_scrape()
    print(f"\n💾 Cache scraping : {len(cache_scrape)} fiches déjà connues.")

    regions = get_regions()
    if not regions:
        return

    print(f"\n📥 Collecte des URLs ({len(regions)} régions)...")
    items_actuels = []
    for r in tqdm(regions, desc="Régions"):
        items_actuels.extend(get_urls_region(r))
    print(f"   → {len(items_actuels)} fiches trouvées sur le site.")

    urls_connues = set(cache_scrape.keys())
    items_nouveaux = [it for it in items_actuels if it["url"] not in urls_connues]
    print(f"   🆕 Nouvelles fiches à scraper : {len(items_nouveaux)}")

    if items_nouveaux:
        print(f"\n🔍 Scraping des nouvelles fiches ({MAX_THREADS} threads)...")
        nouvelles_fiches = []
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as ex:
            futures = {ex.submit(scraper_fiche, it): it for it in items_nouveaux}
            for fut in tqdm(as_completed(futures), total=len(futures), desc="Fiches"):
                nouvelles_fiches.append(fut.result())

        for fiche in nouvelles_fiches:
            if fiche.get("url"):
                cache_scrape[fiche["url"]] = fiche

        sauver_cache_scrape(cache_scrape)
        print(f"   💾 Cache mis à jour : {len(cache_scrape)} fiches.")
    else:
        print("   → Aucune nouvelle fiche.")

    urls_site = {it["url"] for it in items_actuels}
    resultats = [fiche for url, fiche in cache_scrape.items() if url in urls_site]
    print(f"\n📊 Total fiches actives : {len(resultats)}")

    for fiche in resultats:
        if not fiche.get("lat") or not fiche.get("lon"):
            fiche["lat"] = None
            fiche["lon"] = None

    resultats = geocoder(resultats, polygones)

    for fiche in resultats:
        if fiche.get("url") and fiche.get("lat"):
            cache_scrape[fiche["url"]] = fiche
    sauver_cache_scrape(cache_scrape)

    sauvegarder_csv(resultats, os.path.join(OUTPUT_DIR, "urgences_quebec.csv"))

    par_region = defaultdict(list)
    for ev in resultats:
        par_region[ev.get("region", "")].append(ev)

    print("\n🗺️  Génération des cartes...")
    stats = []
    for region, evs in tqdm(par_region.items(), desc="Cartes"):
        fname = nom_fichier(region)
        n = generer_carte_region(region, evs, os.path.join(OUTPUT_DIR, fname))
        stats.append((region, n, fname))

    generer_accueil(stats, os.path.join(OUTPUT_DIR, "index.html"))

    print("\n✅ Terminé !")
    print(f"   Site : {OUTPUT_DIR}/index.html")


if __name__ == "__main__":
    main()