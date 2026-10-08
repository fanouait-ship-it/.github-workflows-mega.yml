"""Regroupe les fichiers en parties <= MAX_GB (sans jamais couper un fichier)
puis envoie chaque partie sur MEGA avec megatools (une seule connexion par partie).

Usage : python upload.py <dossier_téléchargé>
Variables d'environnement :
  MEGA_FOLDER   dossier de destination sous /Root (ex: Videos)
  MAX_GB        taille max d'une partie en Go (défaut 10)
  DELETE_AFTER  "1" pour supprimer les fichiers d'une partie une fois envoyée
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

root = sys.argv[1]
dest = "/Root/" + os.environ["MEGA_FOLDER"].strip("/")
max_bytes = float(os.environ.get("MAX_GB", "10")) * 1024**3
delete_after = os.environ.get("DELETE_AFTER", "0") == "1"

# Erreurs de connexion / blocage : on s'arrête, on ne réessaie JAMAIS
FATAL = re.compile(r"blocked|EBLOCKED|EACCESS|login|credential|bad (user|password)", re.I)

# --- 1. Liste des fichiers -------------------------------------------------
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

# --- 2. Regroupement séquentiel : un fichier n'est jamais découpé ----------
batches, current, size = [], [], 0
for p, s in files:
    if s > max_bytes:
        print(f"⚠️  {p} fait {s / 1024**3:.1f} Go (> limite) : envoyé seul, non découpé.")
    if current and size + s > max_bytes:
        batches.append((current, size))
        current, size = [], 0
    current.append(p)
    size += s
if current:
    batches.append((current, size))

print(f"{len(files)} fichier(s) -> {len(batches)} partie(s) vers {dest}")


# --- 3. Outils -------------------------------------------------------------
def run_mega(args, retries=3):
    """Lance megatools. Réessaie sur erreur réseau, mais jamais sur erreur de login."""
    for attempt in range(1, retries + 1):
        r = subprocess.run(["megatools", *args], capture_output=True, text=True)
        out = (r.stdout + r.stderr).strip()
        if out:
            print(out)
        if r.returncode == 0:
            return True
        if FATAL.search(out):
            sys.exit("Connexion MEGA refusée ou compte bloqué : arrêt (aucun nouvel essai).")
        if attempt < retries:
            time.sleep(90 * attempt)
    return False


def stage(paths):
    """Dossier temporaire contenant uniquement les fichiers de la partie (liens, pas de copie)."""
    base = os.path.dirname(os.path.abspath(root))
    tmp = tempfile.mkdtemp(prefix="stage_", dir=base)
    for p in paths:
        target = os.path.join(tmp, os.path.relpath(p, root))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        try:
            os.link(p, target)
        except OSError:
            os.symlink(os.path.abspath(p), target)
    return tmp


# --- 4. Envoi --------------------------------------------------------------
# Dossier racine de destination (ignoré s'il existe déjà)
run_mega(["mkdir", dest], retries=1)

failed = 0
for i, (paths, total) in enumerate(batches, 1):
    print(f"\n=== Partie {i}/{len(batches)} : {len(paths)} fichier(s), {total / 1024**3:.2f} Go")
    tmp = stage(paths)
    try:
        # copy envoie tout l'arbre d'un coup et crée les sous-dossiers tout seul
        ok = run_mega(["copy", "--no-progress", "-l", tmp, "-r", dest])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if ok:
        print(f"Partie {i} envoyée.")
        if delete_after:
            for p in paths:
                os.remove(p)
    else:
        failed += 1
        print(f"Partie {i} en échec.")

    if i < len(batches):
        time.sleep(30)  # pause entre deux connexions

if failed:
    sys.exit(f"{failed} partie(s) en échec sur {len(batches)}.")
print("\nTout est envoyé.")