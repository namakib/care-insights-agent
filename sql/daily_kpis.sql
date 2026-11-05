-- Step 2: the metrics layer. One row per day with the core Customer Care KPIs.
-- Written in standard SQL; it runs on SQLite here and needs only the table
-- name changed to run on BigQuery (e.g. `project.dataset.tickets`).

SELECT
    created_date                                              AS day,
    COUNT(*)                                                  AS contacts,
    ROUND(AVG(csat), 2)                                       AS csat_avg,
    ROUND(AVG(CASE WHEN csat <= 2 THEN 1.0 ELSE 0 END), 3)    AS dsat_rate,      -- share of unhappy customers
    ROUND(AVG(cost_usd), 2)                                   AS cost_per_contact,
    ROUND(AVG(CASE WHEN category = 'refund' THEN 1.0 ELSE 0 END), 3) AS refund_share,
    ROUND(AVG(first_contact_resolved * 1.0), 3)               AS fcr_rate        -- first-contact resolution
FROM tickets
GROUP BY created_date
ORDER BY created_date;
