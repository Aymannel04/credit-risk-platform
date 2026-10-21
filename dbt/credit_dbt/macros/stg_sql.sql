{#- The staging SQL of credit/freddie/staging.py, written once and used for the main vintages and for the fresh vintages. -#}

{% macro stg_orig_sql(years) -%}
with typed as (
  select
    loan_seq,
    case when try_cast(substr(loan_seq, 2, 2) as integer) >= 90 then 1900 else 2000 end
      + try_cast(substr(loan_seq, 2, 2) as integer)                  as vintage_year,
    try_cast(substr(loan_seq, 5, 1) as integer)                      as vintage_quarter,
    case when {{ int_or_null('credit_score') }} between 300 and 850
         then {{ int_or_null('credit_score') }} end                  as credit_score,
    {{ month_start('first_payment_date') }}                          as first_payment_date,
    {{ month_start('maturity_date') }}                               as maturity_date,
    {{ one_of('first_time_homebuyer', ['Y', 'N']) }}                 as first_time_homebuyer,
    nullif(msa, '')                                                  as msa,
    {{ int_or_null('mi_pct', '999') }}                               as mi_pct,
    {{ int_or_null('n_units', '99') }}                               as n_units,
    {{ one_of('occupancy', ['P', 'I', 'S']) }}                       as occupancy,
    {{ int_or_null('cltv', '999') }}                                 as cltv,
    {{ int_or_null('dti', '999') }}                                  as dti,
    try_cast(nullif(orig_upb, '') as double)                         as orig_upb,
    {{ int_or_null('ltv', '999') }}                                  as ltv,
    try_cast(nullif(int_rate, '') as double)                         as int_rate,
    {{ one_of('channel', ['R', 'B', 'C', 'T']) }}                    as channel,
    {{ one_of('ppm_flag', ['Y', 'N']) }}                             as ppm_flag,
    nullif(amort_type, '')                                           as amort_type,
    nullif(state, '')                                                as state,
    {{ one_of('property_type', ['SF', 'PU', 'CO', 'MH', 'CP']) }}    as property_type,
    nullif(zip3, '')                                                 as zip3,
    {{ one_of('purpose', ['P', 'C', 'N', 'R']) }}                    as purpose,
    {{ int_or_null('orig_term') }}                                   as orig_term,
    {{ int_or_null('n_borrowers', '99') }}                           as n_borrowers,
    nullif(seller_name, '')                                          as seller_name,
    {{ one_of('super_conforming', ['Y', 'N']) }}                     as super_conforming,
    nullif(program_indicator, '')                                    as program_indicator,
    coalesce(relief_refi = 'Y', false)                               as relief_refi,
    {{ one_of('io_indicator', ['Y', 'N']) }}                         as io_indicator
  from read_parquet({{ raw_files('orig', years) }}, union_by_name = true)
)
select
  *,
  (date_part('year', first_payment_date) * 12 + date_part('month', first_payment_date))
    - (vintage_year * 12 + (vintage_quarter - 1) * 3 + 1)            as months_after_vintage,
  ((date_part('year', first_payment_date) * 12 + date_part('month', first_payment_date))
    - (vintage_year * 12 + (vintage_quarter - 1) * 3 + 1)) > 6       as is_seasoned_or_modified
from typed
{%- endmacro %}

{% macro stg_label_sql(years) -%}
with p as (
  select
    loan_seq,
    try_cast(loan_age as integer)                                                       as age,
    coalesce(try_cast(delinq_status as integer) >= 3 or delinq_status = 'RA', false)    as late90,
    coalesce(zero_balance_code in ('02', '03', '09', '15'), false)                      as credit_event,
    coalesce(zero_balance_code is not null, false)                                      as ended,
    coalesce(borrower_assist_code is not null, false)                                   as assist
  from read_parquet({{ raw_files('perf', years) }}, union_by_name = true)
),
per_loan as (
  select
    loan_seq,
    max(age)                                                                            as max_age,
    coalesce(bool_or(ended and age <= {{ var('window_months') }}), false)               as ended_in_window,
    coalesce(bool_or((late90 or credit_event) and age <= {{ var('window_months') }}), false) as def_a,
    coalesce(bool_or(((late90 and not assist) or credit_event)
                     and age <= {{ var('window_months') }}), false)                     as def_b,
    coalesce(bool_or(credit_event and age <= {{ var('window_months') }}), false)        as def_c
  from p
  group by loan_seq
)
select
  loan_seq,
  max_age,
  (max_age >= {{ var('window_months') }} or ended_in_window)                            as observable_24m,
  case when (max_age >= {{ var('window_months') }} or ended_in_window) then cast(def_b as integer) end as default_24m,
  case when (max_age >= {{ var('window_months') }} or ended_in_window) then cast(def_a as integer) end as default_24m_all_late,
  case when (max_age >= {{ var('window_months') }} or ended_in_window) then cast(def_c as integer) end as default_24m_loss_only
from per_loan
{%- endmacro %}
