"""
Génère regions_quebec.geojson avec les polygones des 17 régions
administratives du Québec, à partir des données officielles ouvertes
du ministère des Ressources naturelles et des Forêts (Données Québec,
licence CC-BY 4.0) :
https://www.donneesquebec.ca/recherche/dataset/decoupages-administratifs

(Remplace l'ancienne version qui utilisait des rectangles approximatifs
dessinés à la main — ceux-ci généraient de faux rejets/acceptations dans
le contrôle de cohérence du géocodage.)
"""
import json
import requests
from shapely.geometry import shape, mapping

REST_URL = (
    "https://servicescarto.mern.gouv.qc.ca/pes/rest/services/"
    "Territoire/SDA_WMS/MapServer/0/query"
)

# La source officielle utilise un tiret court (–) ; le reste du projet
# (noms de fichiers, filtres, ZOOM_REGIONS) utilise un tiret cadratin (—).
CORRECTIONS_NOM = {
    "Saguenay–Lac-Saint-Jean": "Saguenay—Lac-Saint-Jean",
    "Gaspésie–Îles-de-la-Madeleine": "Gaspésie—Îles-de-la-Madeleine",
}

# Tolérance de simplification (en degrés, ~300 m) : largement suffisant
# pour un test d'appartenance à une région, et réduit le fichier d'environ
# 13 Mo à ~350 Ko.
TOLERANCE_SIMPLIFICATION = 0.003


def telecharger_regions():
    params = {
        "where": "1=1",
        "outFields": "RES_NM_REG",
        "f": "geojson",
        "outSR": "4326",
    }
    r = requests.get(REST_URL, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def main():
    data = telecharger_regions()

    features = []
    for feat in data.get("features", []):
        nom = feat["properties"].get("RES_NM_REG", "")
        if "Tracé" in nom:
            # Variante historique (frontière Québec-Labrador de 1927) du
            # Côte-Nord : on garde uniquement le tracé courant.
            continue
        nom = CORRECTIONS_NOM.get(nom, nom)

        geom = shape(feat["geometry"]).simplify(
            TOLERANCE_SIMPLIFICATION, preserve_topology=True
        )
        features.append({
            "type": "Feature",
            "properties": {"nom": nom},
            "geometry": mapping(geom),
        })

    print(f"   → {len(features)} régions récupérées.")

    geojson = {"type": "FeatureCollection", "features": features}
    with open("regions_quebec.geojson", "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    print(f"regions_quebec.geojson généré ({len(features)} régions)")


if __name__ == "__main__":
    main()
