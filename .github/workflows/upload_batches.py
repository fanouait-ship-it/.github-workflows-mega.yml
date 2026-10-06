#!/usr/bin/env python3
"""Regroupe les fichiers en parties <= MAX_GB (sans jamais couper un fichier)
puis envoie chaque partie sur MEGA avec megatools."""
import os
import subprocess
import sys

root = sys.argv[1]
dest = "/Root/" + os.environ["MEGA_FOLDER"].strip("/")
max_bytes = float(os.environ.get("MAX_GB", "10")) * 1024**3

files = []
for d, _, names in os.walk(root):
    for n in names:
        if n.endswith(".aria2"):
            continue
        p = os.path.join(d, n)
        files.append((p, os.path.getsize(p)))
files.sort()

if not files:
    sys.exit("Aucun fichier téléchargé.")

# Regroupement séquentiel : un fichier n'est jamais découpé
batches, current, size = [], [], 0
for p, s in files:
    if s > max_bytes:
        print(f"⚠️  {p} fait {s/1024**3:.1f} Go (> limite) : envoyé seul, non découpé.")
    if current and size + s > max_bytes:
        batches.append(current)
        current, size = [], 0
    current.append((p, s))
    size += s
if current:
    batches.append(current)

multi = len(batches) > 1
print(f"{len(files)} fichier(s) -> {len(batches)} partie(s)")

for i, batch in enumerate(batches, 1):
    target = f"{dest}/part{i}" if multi else dest
    print(f"\n=== Partie {i}/{len(batches)} -> {target} ===")
    subprocess.run(["megatools", "mkdir", target], check=False)
    for p, s in batch:
        # on garde l'arborescence relative (sous-dossiers du torrent)
        rel = os.path.dirname(os.path.relpath(p, root))
        sub = f"{target}/{rel}" if rel else target
        if rel:
            subprocess.run(["megatools", "mkdir", sub], check=False)
        subprocess.run(
            ["megatools", "put", "--no-progress", "--path", sub, p], check=True
        )
        os.remove(p)  # libère l'espace disque du runner
        print(f"✅ {os.path.basename(p)} ({s/1024**3:.2f} Go)")
print("\nTerminé.")