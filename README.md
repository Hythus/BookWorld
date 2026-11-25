# BookWorld — Pipeline Data & API REST (RNCP)

## Contexte du projet

**BookWorld** est une entreprise fictive spécialisée dans la vente de livres en ligne souhaitant mieux piloter son activité à l'international. Ses données étant dispersées entre plusieurs sources hétérogènes, ce projet met en place un **pipeline de données complet** permettant de :

1. **Collecter** les données depuis un CSV de ventes, une base SQLite de référentiels, le site web `books.toscrape.com` (première page du catalogue) et les APIs publiques Frankfurter et VATEstimator.
2. **Nettoyer, typer et enrichir** les données tout en respectant le **RGPD** (exclusion des noms et prénoms clients).
3. **Stocker** les données dans une base SQLite finale relationnelle (`database/bookworld.db`) structurée par `schema_final.sql`.
4. **Exposer** l'indicateur métier des ventes agrégées par pays (`sales_by_country`) via une **API REST FastAPI** sécurisée par token.

---

## Architecture & principaux fichiers du projet

```text
BookWorld/
├── pipeline.py                         # Point d'entrée principal du pipeline (collecte -> SQLite)
├── api.py                              # API REST FastAPI sécurisée par Bearer Token
├── schema_final.sql                    # Schéma DDL de la base finale (PK, FK, NOT NULL, RGPD)
├── .env.example                        # Modèle de configuration du token API (sans secret)
├── requirements.txt                    # Liste des librairies Python (compatible pip)
├── pyproject.toml                      # Dépendances Python du projet (gérées avec uv)
├── uv.lock                             # Verrouillage exact des versions de packages
├── Sources/
│   ├── base_de_donneees_bookworld.csv  # Ventes brutes (renommé sans accent)
│   └── bookworld_reference.db          # Base SQLite source des référentiels métier
├── database/
│   └── bookworld.db                    # Base SQLite finale générée par pipeline.py
├── notebooks/
│   ├── RNCP.ipynb                      # Notebook de développement pas à pas
│   └── RNCP.py                         # Version Python synchronisée avec jupytext
└── rapport/
    ├── queries.sql                     # Requêtes SQL d'extraction filtrée et d'agrégation finale
    ├── schema bdd finale.png           # Capture du schéma relationnel de la base finale
    └── diagramme db.jpeg               # Diagramme d'architecture / modélisation
```

| Fichier / Dossier | Rôle |
| :--- | :--- |
| `pipeline.py` | Orchestre toute la chaîne d'extraction, de nettoyage/typage RGPD, de création de `database/bookworld.db` (via `schema_final.sql`) et de calcul de `sales_by_country`. |
| `api.py` | Expose les données de `sales_by_country` via FastAPI (`GET /health` public, `GET /sales-by-country` protégé par Bearer Token). |
| `schema_final.sql` | Définit les 5 tables finales (`books`, `countries`, `exchange_rates`, `sales`, `sales_by_country`) avec leurs clés primaires et étrangères. |
| `rapport/queries.sql` | Regroupe les versions finales commentées des requêtes SQL utilisées (extraction filtrée `EUR`/`GBP` et agrégation `sales_by_country`). |
| `database/bookworld.db` | Base SQLite finale exploitable par l'API et les outils BI, conforme RGPD. |
| `Sources/` | Données brutes d'entrée (non modifiées par le pipeline). |
| `notebooks/` | Notebook exploratoire (`RNCP.ipynb`) maintenu synchronisé en `.py` (`RNCP.py`) grâce à `jupytext`. |
| `.env.example` | Modèle à copier en `.env` pour définir la variable `API_TOKEN`. |
| `requirements.txt` | Liste complète des librairies Python pour une installation standard via `pip`. |
| `pyproject.toml` / `uv.lock` | Déclaration et verrouillage de l'environnement Python (`>= 3.13`). |

---

## 1. Prérequis & installation des dépendances

### Prérequis
- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** (recommandé) ou `pip`

### Cloner le dépôt

En **SSH** (recommandé si votre clé SSH est configurée sur GitHub) :

```powershell
git clone git@github.com:Hythus/BookWorld.git
cd BookWorld
```

En **HTTPS** :

```powershell
git clone https://github.com/Hythus/BookWorld.git
cd BookWorld
```

### Installer les librairies

- **Option A — avec `uv` (recommandé) :**
  ```powershell
  uv sync
  ```

- **Option B — avec `pip` et `requirements.txt` :**
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  ```

### Principales librairies utilisées
- **Traitement & base de données** : `pandas` (manipulation, nettoyage et agrégation des données), `sqlite3` (bibliothèque standard Python pour SQLite), `pathlib` (gestion des chemins).
- **Collecte web & APIs** : `requests` (requêtes HTTP vers `books.toscrape.com`, Frankfurter et VATEstimator), `beautifulsoup4` (parsing HTML lors du scraping).
- **API REST & sécurité** : `fastapi` (framework de l'API REST et Swagger `/docs`), `uvicorn` (serveur ASGI), `python-dotenv` (chargement du token depuis `.env`), `os` & `secrets` (bibliothèque standard pour lire et comparer le token en toute sécurité).
- **Notebooks & exploration** : `jupyter`, `ipykernel`, `jupytext` (synchronisation `.ipynb` ↔ `.py`), ainsi que `numpy`, `openpyxl`, `matplotlib`, `seaborn` et `plotly`.

---

## 2. Authentification : Token API et clé SSH

### A. Token API (`API_TOKEN`) pour interroger l'API

L'endpoint `GET /sales-by-country` est protégé par un **Bearer Token** transmis dans l'en-tête HTTP `Authorization` et comparé côté serveur à la variable d'environnement `API_TOKEN` (chargée depuis `.env`).

1. **Récupérer le token** :
   - **En environnement partagé / évaluation** : demander le token actif à l'administrateur du projet (par messagerie interne ou canal sécurisé).
   - **En local (auto-hébergement)** : choisir votre propre valeur secrète.
2. **Créer le fichier `.env`** à partir du modèle `.env.example` :
   ```powershell
   # PowerShell (Windows)
   Copy-Item .env.example .env
   ```
   ```bash
   # Linux / macOS
   cp .env.example .env
   ```
3. **Renseigner le token dans `.env`** :
   ```env
   API_TOKEN=votre_token_secret_ici
   ```

> **Sécurité :** `.env` est listé dans `.gitignore` et n'est jamais versionné sur GitHub.

### B. Clé SSH (accès GitHub / serveur distant)

- **Sur GitHub** : la clé SSH (paire générée via `ssh-keygen`, dont seule la clé publique `.pub` est ajoutée dans *GitHub → Settings → SSH and GPG keys*) permet de cloner, tirer et pousser le dépôt sans saisir de mot de passe.
- **Sur serveur distant (en production)** : si l'API est hébergée sur un serveur privé non exposé publiquement, un **tunnel SSH** (`ssh -L 8000:127.0.0.1:8000 user@serveur`) permet d'accéder localement à l'API de manière chiffrée.
- **Règle d'or** : ne jamais partager ni pousser une clé privée SSH dans un dépôt Git.

---

## 3. Exécuter le pipeline (`pipeline.py`)

Pour collecter les données et générer (ou mettre à jour) la base finale `database/bookworld.db` :

```powershell
uv run python pipeline.py
```

### Étapes réalisées par `pipeline.py`
1. **Lecture des sources locales** : chargement du CSV des ventes (`Sources/base_de_donneees_bookworld.csv`, renommé sans accent pour éviter les écarts d'encodage Unicode macOS/Windows) et extraction SQL filtrée des pays en `EUR` ou `GBP` depuis `Sources/bookworld_reference.db`.
2. **Scraping web (`books.toscrape.com`)** : collecte des 20 livres de la page 1 (`titre`, `categorie`, `prix_ht`, `prix_ttc`) avec `timeout=10` et gestion des erreurs réseau.
3. **Taux de change historiques (API Frankfurter)** : récupération des taux `GBP → EUR` sur la plage `min..max` des dates de commandes (en une seule requête HTTP par lot), report du dernier jour ouvré pour les week-ends/fériés, puis filtrage sur les 127 dates exactes de commandes.
4. **Enrichissement TVA (API VATEstimator)** : détection des pays présents dans les ventes mais absents du référentiel (`NL`) et ajout automatique dans `countries`.
5. **Nettoyage, typage & conformité RGPD** :
   - typage explicite (`DATE` pour les dates, `float` pour les prix/taux, `int` pour les quantités),
   - normalisation des titres de livres (`strip()` + `lower()`),
   - **suppression des colonnes nominatives** `customer_first_name` et `customer_last_name` (principe de minimisation des données — **Article 5.1.c du RGPD**).
6. **Création de la base finale & agrégation** : application de `schema_final.sql` dans `database/bookworld.db` (clés primaires et étrangères activées), insertion des données propres, puis calcul et sauvegarde de la table agrégée `sales_by_country`.

---

## 4. Lancer et utiliser l'API REST (`api.py`)

Démarrer le serveur FastAPI avec Uvicorn :

```powershell
uv run uvicorn api:app --reload
```

Ouvrir la documentation interactive **Swagger UI** dans le navigateur :
- `http://127.0.0.1:8000/docs`

### Endpoints disponibles

| Méthode | Route | Auth | Codes HTTP | Description |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/health` | Publique | `200` | Indique si l'API et `database/bookworld.db` sont opérationnelles |
| `GET` | `/sales-by-country` | Bearer Token | `200`, `401`, `500` | Retourne les ventes agrégées de tous les pays |
| `GET` | `/sales-by-country?country_code=FR` | Bearer Token | `200`, `401`, `404`, `500` | Filtre les ventes agrégées sur un code pays donné |

### Tester l'API

- **Dans Swagger (`/docs`)** :
  1. Cliquer sur **Authorize** (en haut à droite).
  2. Coller la valeur de `API_TOKEN` (issue du fichier `.env`) et valider.
  3. Exécuter `GET /sales-by-country` (avec ou sans `country_code`).

- **En ligne de commande (`curl`)** :
  ```bash
  # Vérifier l'état de l'API (public)
  curl http://127.0.0.1:8000/health

  # Récupérer tous les pays (authentifié)
  curl -H "Authorization: Bearer votre_token_secret_ici" http://127.0.0.1:8000/sales-by-country

  # Filtrer sur la France (authentifié)
  curl -H "Authorization: Bearer votre_token_secret_ici" "http://127.0.0.1:8000/sales-by-country?country_code=FR"
  ```

- **En PowerShell (`Invoke-RestMethod`)** :
  ```powershell
  $headers = @{ Authorization = "Bearer votre_token_secret_ici" }
  Invoke-RestMethod "http://127.0.0.1:8000/sales-by-country?country_code=FR" -Headers $headers
  ```

### Exemple de réponse JSON (`GET /sales-by-country?country_code=FR`)

```json
[
  {
    "country_code": "FR",
    "country_name": "France",
    "total_orders": 56,
    "total_quantity": 130,
    "total_revenue_gbp": 3979.2,
    "total_revenue_gbp_ttc": 4775.04,
    "total_revenue_eur": 4718.74,
    "total_revenue_eur_ttc": 5662.48
  }
]
```
