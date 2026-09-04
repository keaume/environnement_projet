# 🌿 Urgences environnementales Québec

Carte interactive des interventions d'urgence environnementale au Québec, basée sur les données publiques du MELCCFP.

---

## 🔗 Accès au site

👉 https://keaume.github.io/environnement_projet/

---

## 📌 Fonctionnalités

* 🗺️ Cartes interactives par région
* 🔎 Barre de recherche d'adresse sur chaque carte (Nominatim)
* 📍 Géocodage des événements (Nominatim - OpenStreetMap)
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
git clone https://github.com/keaume/environnement_projet.git
```

### 2. Installer les dépendances

```bash
pip install requests beautifulsoup4 folium tqdm shapely
```

---

## ▶️ Utilisation

```bash
cd docs
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
  ├── index.html              ← page d'accueil (générée)
  ├── carte_*.html             ← une carte par région (générées)
  ├── urgences_quebec.csv      ← données géocodées (généré)
  ├── erreurs_geocode.csv      ← événements non localisables (généré)
  ├── scraper_urgence_env.py   ← script principal (scraping + géocodage + génération des cartes)
  ├── cache_fiches.json        ← cache des fiches scrapées
  ├── cache_geocode.json       ← cache des requêtes de géocodage
  └── regions_quebec.geojson   ← polygones approximatifs des 17 régions (contrôle de cohérence)
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
* Nominatim peut rejeter certaines requêtes, ou mal résoudre un nom de secteur/quartier ambigu (ex. deux villes différentes ayant un secteur du même nom)
* Un contrôle de cohérence (polygone approximatif de la région) rejette les résultats de géocodage manifestement hors région ; les événements non localisables de façon fiable sont exclus des cartes et listés dans `erreurs_geocode.csv` plutôt que placés au mauvais endroit

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
