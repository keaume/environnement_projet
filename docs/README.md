# 🌿 Urgences environnementales Québec

Carte interactive des interventions d'urgence environnementale au Québec, basée sur les données publiques du MELCCFP.

---

## 🔗 Accès au site

👉 https://keaume.github.io/environnement_projet/

---

## 📌 Fonctionnalités

* 🗺️ Cartes interactives par région
* 📍 Géocodage des adresses (Nominatim - OpenStreetMap)
* ⚡ Mise à jour rapide grâce au cache
* 🎯 Filtres dynamiques :

  * Municipalité
  * Type d'événement
  * Masquer les localisations approximatives
* 📊 Données exportées en CSV
* 🔄 Mise à jour automatique via script

---

## 🧠 Fonctionnement

Le script :

1. Scrape les données du site du gouvernement
2. Met en cache les fiches déjà récupérées
3. Géocode les adresses (avec cache pour éviter les requêtes inutiles)
4. Génère :

   * des cartes HTML (Leaflet/Folium)
   * un fichier CSV
   * une page d’accueil (`index.html`)

---

## ⚙️ Installation

### 1. Cloner le projet

```bash
git clone https://keaume.github.io/environnement_projet/
```

### 2. Installer les dépendances

```bash
pip install requests beautifulsoup4 folium tqdm shapely
```

---

## ▶️ Utilisation

```bash
python scraper_urgence_env.py
```

---

## 🔄 Mise à jour des données

Lorsque de nouveaux événements apparaissent :

```bash
git add .
git commit -m "update data"
git push
```

👉 GitHub Pages met automatiquement le site à jour (≈ 1 min)

---

## 📁 Structure du projet

```
/docs
  ├── index.html
  ├── carte_*.html
  ├── urgences_quebec.csv
  ├── erreurs_geocode.csv

scraper_urgence_env.py
cache_fiches.json
cache_geocode.json
regions_quebec.geojson
```

---

## ⚡ Optimisations

* Cache scraping → évite de re-scraper inutilement
* Cache géocodage → limite les appels API
* Nominatim (100% gratuit)

---

## ⚠️ Limitations

* Certaines adresses sont approximatives (centre-ville, etc.)
* Dépendance à la qualité des données source
* Nominatim peut rejeter certaines requêtes

---

## 👨‍💻 Auteur

**Antoine Toenz**
📧 [antoine@toenz.com](mailto:antoine@toenz.com)

---

## 📜 Licence

Projet personnel – utilisation libre à des fins éducatives et analytiques.

---

## 🚀 Améliorations possibles

* Heatmap des incidents
* Graphiques (évolution temporelle)
* Filtres avancés (date, gravité)
* Mise à jour automatique (GitHub Actions)
* API backend

---

## 🧾 Source des données

Données issues du MELCCFP (Québec)
https://www.environnement.gouv.qc.ca/

---

## ❤️ Remarque

Ce projet est un outil d’analyse et de visualisation.
Les données affichées peuvent contenir des imprécisions.
