{#- The table of the 4 FRESH vintages (the v2 exam). Same exclusions and same rate spread as mart_loan_features
    (credit/freddie/fresh.py). Their labels were locked until the model was frozen; the exam is done, so they are built here. -#}
with joined as (
  select o.*, l.observable_24m, l.default_24m, l.default_24m_all_late, l.default_24m_loss_only
  from {{ ref('stg_orig_fresh') }} o
  join {{ ref('stg_label_fresh') }} l using (loan_seq)
),
kept as (
  select * from joined
  where not relief_refi and not is_seasoned_or_modified and observable_24m
),
spread as (
  select *,
    int_rate - quantile_cont(int_rate, 0.5)
      over (partition by vintage_year, vintage_quarter, (orig_term > {{ var('short_term_months') }})) as rate_spread,
    case when n_borrowers is null then null when n_borrowers >= 2 then 1.0 else 0.0 end as several_borrowers
  from kept
)
select {{ fresh_feature_columns() }}, 'fresh_' || cast(vintage_year as varchar) as split
from spread
