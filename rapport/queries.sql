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
        prix_ht,
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
)
SELECT
    s.country_code,
    p.country_name,
    COUNT(DISTINCT s.order_id) AS total_orders,
    SUM(COALESCE(s.quantity, 1)) AS total_quantity,
    ROUND(
        SUM(l.prix_ht * COALESCE(s.quantity, 1) * (1 - COALESCE(s.discount_rate, 0)) * (1 + p.vat_rate / 100.0)),
        2
    ) AS total_revenue_gbp,
    ROUND(
        SUM(l.prix_ht * COALESCE(s.quantity, 1) * (1 - COALESCE(s.discount_rate, 0)) * (1 + p.vat_rate / 100.0) * er.rate),
        2
    ) AS total_revenue_eur,
    ROUND(
        SUM(l.prix_ht * COALESCE(s.quantity, 1) * (1 - COALESCE(s.discount_rate, 0)) * (p.vat_rate / 100.0) * er.rate),
        2
    ) AS total_vat_eur,
    ROUND(
        SUM(l.prix_ht * COALESCE(s.quantity, 1) * (1 - COALESCE(s.discount_rate, 0)) * er.rate),
        2
    ) AS total_tax_excl_eur
FROM sales s
LEFT JOIN livres l
    ON s.book_name = l.titre
LEFT JOIN pays p
    ON s.country_code = p.country_code
LEFT JOIN exchange_rates er
    ON s.order_date = er.rate_date
GROUP BY
    s.country_code,
    p.country_name
ORDER BY total_revenue_eur DESC;
