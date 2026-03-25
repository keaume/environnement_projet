import json
from collections import Counter

with open("cache_fiches.json") as f:
    cache = json.load(f)

fiches = list(cache.values()) if isinstance(cache, dict) else cache

munis = Counter(f.get("municipalite","").strip() for f in fiches if f.get("municipalite","").strip())

print(f"Total fiches           : {len(fiches)}")
print(f"Municipalités uniques  : {len(munis)}")
print(f"\nTop 10 :")
for m, n in munis.most_common(10):
    print(f"  {n:4d}x  {m}")