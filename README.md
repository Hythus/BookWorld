# BookWorld

Projet d'analyse de données autour de BookWorld (RNCP).

## Structure du projet

- `notebooks/` : notebooks Jupyter d'exploration et d'analyse
- `src/` : modules et scripts Python réutilisables
- `base_de_données_bookworld.csv` : jeu de données principal au format CSV
- `bookworld_reference.db` : base de données SQLite de référence
- `pyproject.toml` & `uv.lock` : configuration du projet et dépendances gérées avec `uv`

## Prise en main

Installer ou synchroniser l'environnement virtuel avec `uv` :

```powershell
uv sync
```

Activer l'environnement virtuel (PowerShell) :

```powershell
.venv\Scripts\Activate.ps1
```

Lancer un script ou Jupyter Lab :

```powershell
uv run python src/mon_script.py
uv run jupyter lab
```

Ajouter une nouvelle dépendance :

```powershell
uv add <nom-du-package>
```
