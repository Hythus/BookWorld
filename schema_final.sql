-- Schéma final de la base BookWorld (database/bookworld.db)
-- Conforme RGPD : les colonnes nominatives clients (customer_first_name, customer_last_name)
-- sont volontairement exclues de la table sales (principe de minimisation des données).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS books (
    titre TEXT PRIMARY KEY,
    categorie TEXT,
    prix_ht REAL NOT NULL,
    prix_ttc REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS countries (
    country_code TEXT PRIMARY KEY,
    country_name TEXT NOT NULL,
    currency_code TEXT NOT NULL,
    vat_rate REAL NOT NULL,
    region TEXT,
    is_active INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS exchange_rates (
    rate_date DATE PRIMARY KEY,
    base_currency TEXT NOT NULL,
    target_currency TEXT NOT NULL,
    rate REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sales (
    order_id TEXT PRIMARY KEY,
    order_date DATE NOT NULL,
    book_id TEXT NOT NULL,
    country_code TEXT NOT NULL,
    channel_code TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    discount_rate REAL NOT NULL,
    book_name TEXT NOT NULL,
    FOREIGN KEY (book_name) REFERENCES books (titre),
    FOREIGN KEY (country_code) REFERENCES countries (country_code),
    FOREIGN KEY (order_date) REFERENCES exchange_rates (rate_date)
);

CREATE TABLE IF NOT EXISTS sales_by_country (
    country_code TEXT PRIMARY KEY,
    country_name TEXT NOT NULL,
    total_orders INTEGER NOT NULL,
    total_quantity INTEGER NOT NULL,
    total_revenue_gbp REAL NOT NULL,
    total_revenue_eur REAL NOT NULL,
    total_vat_eur REAL NOT NULL,
    total_tax_excl_eur REAL NOT NULL,
    FOREIGN KEY (country_code) REFERENCES countries (country_code)
);
