{#- One row per loan: watched for 24 months or not, and the default label (main vintages). Logic: macros/stg_sql.sql. -#}
{{ stg_label_sql(var('years')) }}
