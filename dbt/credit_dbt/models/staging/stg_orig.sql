{#- One row per loan, typed (main vintages). Nothing is filtered; odd loans are only flagged. Logic: macros/stg_sql.sql. -#}
{{ stg_orig_sql(var('years')) }}
