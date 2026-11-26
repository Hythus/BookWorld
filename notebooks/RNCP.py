# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.7
# ---

# %% [markdown]
# # Partie 1 — Collecte et extraction des données (1.1 & 1.2)
#
# ## 1. Imports, lecture du CSV de ventes et extraction SQLite filtrée
# Chargement des librairies nécessaires, lecture du fichier des ventes (`base_de_donneees_bookworld.csv`) et extraction filtrée de la table de référence `countries` depuis `bookworld_reference.db` (pays en `EUR` ou `GBP` uniquement ; les tables `channels` et `category_rules` ne sont pas utilisées pour le KPI par pays).
#
# *Note :* le fichier CSV source a été renommé sans accent en `base_de_donneees_bookworld.csv` afin d'éviter les problèmes d'encodage Unicode (`é` décomposé macOS vs Windows) lors de la lecture en Python.

# %%
import sqlite3
from pathlib import Path
import pandas as pd
import requests
from bs4 import BeautifulSoup

path = Path("../Sources")
if not path.exists():
    path = Path("Sources")

# Import du CSV des ventes
df_bookworld = pd.read_csv(path / "base_de_donneees_bookworld.csv")

# Extraction SQL filtrée depuis la base SQLite de référence (pays en EUR ou GBP)
query_countries = """
SELECT
    country_code,
    country_name,
    currency_code,
    vat_rate,
    region,
    is_active
FROM countries
WHERE currency_code IN ('EUR', 'GBP');
"""

with sqlite3.connect(path / "bookworld_reference.db") as conn:
    df_countries = pd.read_sql_query(query_countries, conn)

print("Ventes chargées :", df_bookworld.shape)
df_countries

# %% [markdown]
# ## 2. Scraping — Récupération des URLs des livres (page 1)
# Requête sur la première page de `books.toscrape.com` pour collecter les URLs des 20 livres du catalogue, avec timeout et gestion d'erreur réseau.

# %%
# Récupération de la première page du site
url = "https://books.toscrape.com/"
urls_livres = []

try:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")

    # Récupération de l'URL de chaque livre
    livres = soup.find_all("article", class_="product_pod")

    for livre in livres:
        lien = livre.find("h3").find("a")["href"]
        url_complete = url + lien
        urls_livres.append(url_complete)

    print(len(urls_livres), "livres trouvés")
except requests.exceptions.RequestException as e:
    print("Erreur lors de la récupération de la page :", e)

urls_livres[:5]

# %% [markdown]
# ## 3. Scraping — Extraction des informations de chaque livre
# Parcours de chaque URL pour récupérer le titre, la catégorie et le prix TTC (le prix HT sera recalculé en SQL à partir de la TVA de chaque pays), puis construction du DataFrame `df_books`.

# %%
# Parcours de chaque URL pour récupérer titre, catégorie et prix TTC
donnees_livres = []

for url_livre in urls_livres:
    try:
        response = requests.get(url_livre, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        # Titre du livre
        titre = soup.find("h1").text.strip()

        # Catégorie (3ème lien du fil d'Ariane : Home > Books > Catégorie)
        liens_categorie = soup.find("ul", class_="breadcrumb").find_all("a")
        categorie = liens_categorie[2].text.strip()

        # Prix TTC dans le tableau d'informations
        lignes = soup.find("table", class_="table-striped").find_all("tr")
        prix_ttc = None

        for ligne in lignes:
            entete = ligne.find("th").text.strip()
            valeur = ligne.find("td").text.strip()

            if entete == "Price (incl. tax)":
                prix_ttc = float(valeur.replace("£", ""))

        donnees_livres.append({
            "titre": titre,
            "categorie": categorie,
            "prix_ttc": prix_ttc,
        })
    except requests.exceptions.RequestException as e:
        print(f"Erreur réseau sur {url_livre} : {e}")
    except Exception as e:
        print(f"Erreur de lecture sur {url_livre} : {e}")

df_books = pd.DataFrame(donnees_livres)
df_books

# %% [markdown]
# ## 4. API Frankfurter — Récupération des taux de change historiques GBP → EUR
# Appel en une seule requête à l'API publique Frankfurter sur la période des commandes (`min..max`), complétion des week-ends et jours fériés avec le dernier jour ouvré, puis filtrage pour ne conserver dans `df_exchange_rates` que les dates exactes des commandes.
#
# *Choix d'architecture :* l'appel sur la plage `min..max` en une seule requête est privilégié pour ce chargement historique par lot (plus rapide et plus fiable que des appels unitaires par date). Dans une logique de production avec mise à jour quotidienne (incrémentale), on n'interrogerait l'API que pour la date du jour ou les nouvelles dates absentes de la table.

# %%
# Récupération de l'historique des taux GBP -> EUR sur la période des commandes
date_debut = df_bookworld["order_date"].min()
date_fin = df_bookworld["order_date"].max()

url_api = f"https://api.frankfurter.dev/v1/{date_debut}..{date_fin}"
params = {"base": "GBP", "symbols": "EUR"}

df_exchange_rates = pd.DataFrame()

try:
    response = requests.get(url_api, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    lignes_taux = []
    for date_jour, taux in data["rates"].items():
        lignes_taux.append({
            "rate_date": date_jour,
            "base_currency": "GBP",
            "target_currency": "EUR",
            "rate": taux["EUR"],
        })

    df_taux_api = pd.DataFrame(lignes_taux)

    # Compléter tous les jours calendaires (week-ends et jours fériés = dernier taux connu)
    toutes_les_dates = pd.DataFrame({
        "rate_date": pd.date_range(date_debut, date_fin).strftime("%Y-%m-%d")
    })
    df_exchange_rates = toutes_les_dates.merge(df_taux_api, on="rate_date", how="left")
    df_exchange_rates["base_currency"] = "GBP"
    df_exchange_rates["target_currency"] = "EUR"
    df_exchange_rates["rate"] = df_exchange_rates["rate"].ffill().bfill()

    # Ne garder que les dates où une commande a été passée
    dates_commandes = df_bookworld["order_date"].unique()
    df_exchange_rates = df_exchange_rates[
        df_exchange_rates["rate_date"].isin(dates_commandes)
    ].reset_index(drop=True)

    print(f"Taux conservés pour les dates de commandes : {len(df_exchange_rates)} jours")
except requests.exceptions.RequestException as e:
    print("Erreur lors de l'appel à l'API Frankfurter :", e)

df_exchange_rates.head()

# %% [markdown]
# # Partie 2 — Nettoyage, enrichissement, base finale et agrégation (2.1 & 2.2)
#
# ## 5. API VATEstimator — Compléter `df_countries` avec les pays manquants
# Identification des codes pays présents dans `df_bookworld` mais absents de `df_countries`, puis appel à l'API publique VATEstimator (`vatestimator.com/api/v1/rates.json`) pour récupérer leurs informations (nom, devise, taux de TVA, région) et compléter `df_countries`.

# %%
# 1. Trouver les pays présents dans les ventes mais absents de df_countries
pays_manquants = []
for pays in df_bookworld["country_code"].unique():
    if pays not in df_countries["country_code"].values:
        pays_manquants.append(pays)

print("Pays manquants :", pays_manquants)

# 2. Récupérer les infos via l'API VATEstimator et compléter df_countries
url_vat = "https://vatestimator.com/api/v1/rates.json"
nouveaux_pays = []

if len(pays_manquants) > 0:
    try:
        response = requests.get(url_vat, timeout=10)
        response.raise_for_status()
        data_vat = response.json()

        for pays in data_vat["rates"]:
            if pays["code"] in pays_manquants:
                region = "Europe"
                if "eu" not in pays["region"] and "europe" not in pays["region"]:
                    region = pays["region"][0]

                nouveaux_pays.append({
                    "country_code": pays["code"],
                    "country_name": pays["country"],
                    "currency_code": pays["currency_code"],
                    "vat_rate": float(pays["standard_rate"]),
                    "region": region,
                    "is_active": 1,
                })

        df_countries = pd.concat([df_countries, pd.DataFrame(nouveaux_pays)], ignore_index=True)
    except requests.exceptions.RequestException as e:
        print("Erreur lors de l'appel à l'API VATEstimator :", e)

df_countries

# %% [markdown]
# ## 6. Nettoyage et typage des colonnes avant l'export SQLite
# Harmonisation des types (`DATE`, `float`, `int`), normalisation des titres de livres (`strip` + `lower`) pour fiabiliser la jointure, et suppression des noms clients (RGPD) inutiles au pilotage par pays.

# %%
# 1. Dates -> format date (YYYY-MM-DD, type DATE dans SQLite)
df_bookworld["order_date"] = pd.to_datetime(df_bookworld["order_date"]).dt.date
df_exchange_rates["rate_date"] = pd.to_datetime(df_exchange_rates["rate_date"]).dt.date

# 2. Prix -> float
df_books["prix_ttc"] = df_books["prix_ttc"].astype(float)

# 3. Taux -> float
df_bookworld["discount_rate"] = df_bookworld["discount_rate"].astype(float)
df_countries["vat_rate"] = df_countries["vat_rate"].astype(float)
df_exchange_rates["rate"] = df_exchange_rates["rate"].astype(float)

# 4. Quantités -> int
df_bookworld["quantity"] = df_bookworld["quantity"].astype(int)

# 5. Normalisation des titres de livres (trim + minuscules) pour la jointure
df_bookworld["book_name"] = df_bookworld["book_name"].str.strip().str.lower()
df_books["titre"] = df_books["titre"].str.strip().str.lower()

# 6. Suppression des données personnelles clients (RGPD)
df_bookworld = df_bookworld.drop(columns=["customer_first_name", "customer_last_name"], errors="ignore")

# Vérification rapide des types
print("df_bookworld :\n", df_bookworld.dtypes, "\n")
print("df_books :\n", df_books.dtypes, "\n")
print("df_exchange_rates :\n", df_exchange_rates.dtypes)

# %% [markdown]
# ## 7. Création de la base SQLite finale (`database/bookworld.db`)
# Enregistrement des 4 tables propres (`sales`, `books`, `countries`, `exchange_rates`) dans `database/bookworld.db`, sans modifier la base source.

# %%
# Création de la nouvelle base SQLite dans le dossier database/ (sans modifier la base source)
dossier_db = path.resolve().parent / "database"
dossier_db.mkdir(exist_ok=True)
db_finale = dossier_db / "bookworld.db"

with sqlite3.connect(db_finale) as conn:
    df_bookworld.to_sql("sales", conn, if_exists="replace", index=False)
    df_books.to_sql("books", conn, if_exists="replace", index=False)
    df_countries.to_sql("countries", conn, if_exists="replace", index=False)
    df_exchange_rates.to_sql("exchange_rates", conn, if_exists="replace", index=False)

    # Vérification des tables créées
    tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table';", conn)

print(f"Base créée : {db_finale}")
tables

# %% [markdown]
# ## 8. Agrégation SQL — Création de la table finale `sales_by_country`
# Calcul des ventes agrégées par pays : CA TTC en GBP et en EUR à partir de `prix_ttc` (au taux du jour de commande), puis recalcul du CA HT et du montant de TVA en EUR grâce au taux de TVA de chaque pays, et enregistrement dans `database/bookworld.db` pour l'API.

# %%
# Requête SQL d'agrégation des ventes par pays
query_sales_by_country = """
WITH livres AS (
    SELECT
        titre,
        prix_ttc
    FROM books
),
pays AS (
    SELECT
        country_code,
        country_name,
        currency_code,
        vat_rate
    FROM countries
    WHERE currency_code IN ('EUR', 'GBP')
),
ventes_detail AS (
    SELECT
        s.order_id,
        s.country_code,
        p.country_name,
        COALESCE(s.quantity, 1) AS quantite,
        l.prix_ttc * COALESCE(s.quantity, 1) * (1 - COALESCE(s.discount_rate, 0)) AS montant_gbp_ttc,
        l.prix_ttc * COALESCE(s.quantity, 1) * (1 - COALESCE(s.discount_rate, 0)) * er.rate AS montant_eur_ttc,
        (l.prix_ttc * COALESCE(s.quantity, 1) * (1 - COALESCE(s.discount_rate, 0)) * er.rate) / (1 + p.vat_rate / 100.0) AS montant_eur_ht
    FROM sales s
    LEFT JOIN livres l
        ON s.book_name = l.titre
    LEFT JOIN pays p
        ON s.country_code = p.country_code
    LEFT JOIN exchange_rates er
        ON s.order_date = er.rate_date
)
SELECT
    country_code,
    country_name,
    COUNT(DISTINCT order_id) AS total_orders,
    SUM(quantite) AS total_quantity,
    ROUND(SUM(montant_gbp_ttc), 2) AS total_revenue_gbp,
    ROUND(SUM(montant_eur_ttc), 2) AS total_revenue_eur,
    ROUND(SUM(montant_eur_ttc - montant_eur_ht), 2) AS total_vat_eur,
    ROUND(SUM(montant_eur_ht), 2) AS total_tax_excl_eur
FROM ventes_detail
GROUP BY
    country_code,
    country_name
ORDER BY total_revenue_eur DESC;
"""

with sqlite3.connect(db_finale) as conn:
    df_sales_by_country = pd.read_sql_query(query_sales_by_country, conn)
    df_sales_by_country.to_sql("sales_by_country", conn, if_exists="replace", index=False)

df_sales_by_country
