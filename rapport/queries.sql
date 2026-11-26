-- 1. Extraction filtrée des pays en EUR ou GBP depuis Sources/bookworld_reference.db
SELECT
    country_code,
    country_name,
    currency_code,
    vat_rate,
    region,
    is_active
FROM countries
WHERE currency_code IN ('EUR', 'GBP');

-- 2. Enrichissement et agrégation des ventes par pays (sales_by_country) sur database/bookworld.db
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
