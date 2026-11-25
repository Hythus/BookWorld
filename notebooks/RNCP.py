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
# # Partie 1 — Collecte des données BookWorld
#
# ## 1. Imports, lecture du CSV de ventes et extraction SQLite
# Chargement des librairies nécessaires, lecture du fichier des ventes (`base_de_données_bookworld.csv`) et extraction des tables de référence (`channels`, `countries`, `category_rules`) depuis `bookworld_reference.db`.

# %%
import sqlite3
from pathlib import Path
import pandas as pd
import requests
from bs4 import BeautifulSoup

path = Path(r"C:\Users\Deval\Documents\data bird\RNCP\Sources")

# Import du CSV
df_bookworld = pd.read_csv(path / "base_de_données_bookworld.csv")

# Import des tables SQLite
with sqlite3.connect(path / "bookworld_reference.db") as conn:
    df_channels = pd.read_sql_query("SELECT * FROM channels", conn)
    df_countries = pd.read_sql_query("SELECT * FROM countries", conn)
    df_category_rules = pd.read_sql_query("SELECT * FROM category_rules", conn)

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
# Parcours de chaque URL pour récupérer le titre, la catégorie et les prix HT / TTC, puis construction du DataFrame `df_books`.

# %%
# Parcours de chaque URL pour récupérer titre, catégorie et prix HT / TTC
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

        # Prix HT et Prix TTC dans le tableau d'informations
        lignes = soup.find("table", class_="table-striped").find_all("tr")
        prix_ht = None
        prix_ttc = None

        for ligne in lignes:
            entete = ligne.find("th").text.strip()
            valeur = ligne.find("td").text.strip()

            if entete == "Price (excl. tax)":
                prix_ht = float(valeur.replace("£", ""))
            elif entete == "Price (incl. tax)":
                prix_ttc = float(valeur.replace("£", ""))

        donnees_livres.append({
            "titre": titre,
            "categorie": categorie,
            "prix_ht": prix_ht,
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
# ## 6. Création de la nouvelle base SQLite exploitable (`database/bookworld.db`)
# Enregistrement de l'ensemble des données collectées (ventes CSV, catalogue scrapé, référentiels SQLite enrichis avec les pays manquants et table `exchange_rates` issue de l'API Frankfurter) dans une nouvelle base SQLite prête pour les requêtes SQL.

# %%
# Création de la nouvelle base SQLite dans le dossier database/ (sans modifier la base source)
dossier_db = path.parent / "database"
dossier_db.mkdir(exist_ok=True)
db_finale = dossier_db / "bookworld.db"

with sqlite3.connect(db_finale) as conn:
    df_bookworld.to_sql("sales", conn, if_exists="replace", index=False)
    df_books.to_sql("books", conn, if_exists="replace", index=False)
    df_channels.to_sql("channels", conn, if_exists="replace", index=False)
    df_countries.to_sql("countries", conn, if_exists="replace", index=False)
    df_category_rules.to_sql("category_rules", conn, if_exists="replace", index=False)
    df_exchange_rates.to_sql("exchange_rates", conn, if_exists="replace", index=False)

    # Vérification des tables créées
    tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table';", conn)

print(f"Base créée : {db_finale}")
tables
