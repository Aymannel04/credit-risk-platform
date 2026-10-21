{#- The small SQL helpers of credit/freddie/staging.py (_int, _one_of, _month), written as dbt macros. -#}

{% macro raw_files(kind, years) -%}
[{%- for y in years -%}'{{ var('raw_dir') }}/{{ kind }}_{{ y }}.parquet'{%- if not loop.last -%}, {% endif -%}{%- endfor -%}]
{%- endmacro %}

{% macro int_or_null(col, na=none) -%}
{%- set expr = "NULLIF(" ~ col ~ ", '')" -%}
{%- if na is not none -%}{%- set expr = "NULLIF(" ~ expr ~ ", '" ~ na ~ "')" -%}{%- endif -%}
TRY_CAST({{ expr }} AS INTEGER)
{%- endmacro %}

{% macro one_of(col, allowed) -%}
CASE WHEN {{ col }} IN ({%- for a in allowed -%}'{{ a }}'{%- if not loop.last -%}, {% endif -%}{%- endfor -%}) THEN {{ col }} END
{%- endmacro %}

{% macro month_start(col) -%}
CAST(TRY_STRPTIME({{ col }} || '01', '%Y%m%d') AS DATE)
{%- endmacro %}

{#- The columns of the features table, in the order of credit/freddie/features.py (META + FEATURES + LABELS, then split). -#}
{% macro feature_columns() -%}
loan_seq, vintage_year, vintage_quarter, first_payment_date, int_rate,
credit_score, mi_pct, n_units, cltv, dti, orig_upb, ltv, rate_spread, orig_term, n_borrowers,
first_time_homebuyer, occupancy, channel, ppm_flag, property_type, purpose, state, super_conforming,
default_24m, default_24m_all_late, default_24m_loss_only
{%- endmacro %}

{#- Same list for the fresh table: one more input, several_borrowers, before the labels (EXTRA in credit/freddie/fresh.py). -#}
{% macro fresh_feature_columns() -%}
loan_seq, vintage_year, vintage_quarter, first_payment_date, int_rate,
credit_score, mi_pct, n_units, cltv, dti, orig_upb, ltv, rate_spread, orig_term, n_borrowers,
first_time_homebuyer, occupancy, channel, ppm_flag, property_type, purpose, state, super_conforming,
several_borrowers,
default_24m, default_24m_all_late, default_24m_loss_only
{%- endmacro %}
