import json

with open("cache_fiches.json", "r", encoding="utf-8") as f:
    cache = json.load(f)

def fix(s):
    if not isinstance(s, str):
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except Exception:
        return s  # déjà bon, on touche pas

def fix_fiche(fiche):
    return {k: fix(v) for k, v in fiche.items()}

if isinstance(cache, dict):
    cache = {url: fix_fiche(fiche) for url, fiche in cache.items()}
else:
    cache = [fix_fiche(f) for f in cache]

with open("cache_fiches.json", "w", encoding="utf-8") as f:
    json.dump(cache, f, ensure_ascii=False, indent=2)

print("✅ Encodage corrigé")