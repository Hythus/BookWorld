import sqlite3
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
SOURCES_DIR = BASE_DIR / "Sources"
CSV_PATH = SOURCES_DIR / "base_de_donneees_bookworld.csv"
REF_DB_PATH = SOURCES_DIR / "bookworld_reference.db"
DB_FINALE = BASE_DIR / "database" / "bookworld.db"
SCHEMA_PATH = BASE_DIR / "schema_final.sql"


def charger_ventes_et_pays():
    """Charge le CSV des ventes et extrait les pays en EUR ou GBP depuis SQLite."""
    df_bookworld = pd.read_csv(CSV_PATH)

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

    with sqlite3.connect(REF_DB_PATH) as conn:
        df_countries = pd.read_sql_query(query_countries, conn)

    print("Ventes chargées :", df_bookworld.shape)
    return df_bookworld, df_countries


def scraper_urls_livres():
    """Récupère les URLs des livres sur la première page de books.toscrape.com."""
    url = "https://books.toscrape.com/"
    urls_livres = []

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        livres = soup.find_all("article", class_="product_pod")
        for livre in livres:
            lien = livre.find("h3").find("a")["href"]
            urls_livres.append(url + lien)

        print(len(urls_livres), "livres trouvés")
    except requests.exceptions.RequestException as e:
        print("Erreur lors de la récupération de la page :", e)

    return urls_livres


def scraper_details_livres(urls_livres):
    """Parcourt chaque URL de livre pour récupérer titre, catégorie et prix TTC."""
    donnees_livres = []

    for url_livre in urls_livres:
        try:
            response = requests.get(url_livre, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            titre = soup.find("h1").text.strip()
            liens_categorie = soup.find("ul", class_="breadcrumb").find_all("a")
            categorie = liens_categorie[2].text.strip()

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

    return pd.DataFrame(donnees_livres)


def recuperer_taux_change(df_bookworld):
    """Récupère les taux GBP -> EUR via Frankfurter pour chaque date de commande."""
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

        # Compléter les week-ends et jours fériés avec le dernier jour ouvré connu
        toutes_les_dates = pd.DataFrame({
            "rate_date": pd.date_range(date_debut, date_fin).strftime("%Y-%m-%d")
        })
        df_exchange_rates = toutes_les_dates.merge(df_taux_api, on="rate_date", how="left")
        df_exchange_rates["base_currency"] = "GBP"
        df_exchange_rates["target_currency"] = "EUR"
        df_exchange_rates["rate"] = df_exchange_rates["rate"].ffill().bfill()

        # Ne conserver que les dates exactes des commandes
        dates_commandes = df_bookworld["order_date"].unique()
        df_exchange_rates = df_exchange_rates[
            df_exchange_rates["rate_date"].isin(dates_commandes)
        ].reset_index(drop=True)

        print(f"Taux conservés pour les dates de commandes : {len(df_exchange_rates)} jours")
    except requests.exceptions.RequestException as e:
        print("Erreur lors de l'appel à l'API Frankfurter :", e)

    return df_exchange_rates


def completer_pays_manquants(df_bookworld, df_countries):
    """Complète df_countries avec les pays des ventes absents du référentiel via VATEstimator."""
    pays_manquants = []
    for pays in df_bookworld["country_code"].unique():
        if pays not in df_countries["country_code"].values:
            pays_manquants.append(pays)

    print("Pays manquants :", pays_manquants)

    if len(pays_manquants) > 0:
        url_vat = "https://vatestimator.com/api/v1/rates.json"
        nouveaux_pays = []

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

            if nouveaux_pays:
                df_countries = pd.concat(
                    [df_countries, pd.DataFrame(nouveaux_pays)],
                    ignore_index=True,
                )
        except requests.exceptions.RequestException as e:
            print("Erreur lors de l'appel à l'API VATEstimator :", e)

    return df_countries


def nettoyer_et_typer(df_bookworld, df_books, df_countries, df_exchange_rates):
    """Type les colonnes, normalise les titres et retire les noms clients (RGPD)."""
    df_bookworld = df_bookworld.copy()
    df_books = df_books.copy()
    df_countries = df_countries.copy()
    df_exchange_rates = df_exchange_rates.copy()

    # 1. Dates -> format DATE (YYYY-MM-DD)
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
    df_bookworld = df_bookworld.drop(
        columns=["customer_first_name", "customer_last_name"],
        errors="ignore",
    )

    return df_bookworld, df_books, df_countries, df_exchange_rates


def creer_base_finale(df_bookworld, df_books, df_countries, df_exchange_rates):
    """Crée les tables avec schema_final.sql (PK/FK) et y insère les données."""
    DB_FINALE.parent.mkdir(exist_ok=True)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    with sqlite3.connect(DB_FINALE) as conn:
        # Supprimer les anciennes tables dans l'ordre inverse des clés étrangères
        conn.execute("PRAGMA foreign_keys = OFF;")
        for table in ("sales_by_country", "sales", "exchange_rates", "countries", "books"):
            conn.execute(f'DROP TABLE IF EXISTS "{table}";')

        # Appliquer le schéma final (PRIMARY KEY, FOREIGN KEY, NOT NULL)
        conn.executescript(schema_sql)
        conn.execute("PRAGMA foreign_keys = ON;")

        # Insérer d'abord les tables parentes, puis la table sales
        df_books.to_sql("books", conn, if_exists="append", index=False)
        df_countries.to_sql("countries", conn, if_exists="append", index=False)
        df_exchange_rates.to_sql("exchange_rates", conn, if_exists="append", index=False)
        df_bookworld.to_sql("sales", conn, if_exists="append", index=False)

    print(f"Base créée : {DB_FINALE}")


def creer_table_sales_by_country():
    """Calcule l'agrégation SQL sales_by_country et l'enregistre dans database/bookworld.db."""
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

    with sqlite3.connect(DB_FINALE) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        df_sales_by_country = pd.read_sql_query(query_sales_by_country, conn)
        conn.execute("DELETE FROM sales_by_country;")
        df_sales_by_country.to_sql("sales_by_country", conn, if_exists="append", index=False)

    return df_sales_by_country


def main():
    """Point d'entrée principal du pipeline BookWorld."""
    df_bookworld, df_countries = charger_ventes_et_pays()
    urls_livres = scraper_urls_livres()
    df_books = scraper_details_livres(urls_livres)
    df_exchange_rates = recuperer_taux_change(df_bookworld)
    df_countries = completer_pays_manquants(df_bookworld, df_countries)

    if df_books.empty or df_exchange_rates.empty:
        print("Pipeline interrompu : collecte web/API incomplète.")
        return

    df_bookworld, df_books, df_countries, df_exchange_rates = nettoyer_et_typer(
        df_bookworld, df_books, df_countries, df_exchange_rates
    )
    creer_base_finale(df_bookworld, df_books, df_countries, df_exchange_rates)
    df_sales_by_country = creer_table_sales_by_country()

    print("\nVentes agrégées par pays (sales_by_country) :")
    print(df_sales_by_country.to_string(index=False))


if __name__ == "__main__":
    main()
