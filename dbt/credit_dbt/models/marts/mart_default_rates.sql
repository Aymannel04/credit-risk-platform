{#- Business table: how many loans and defaults per vintage and split (the numbers shown in the README and the decision log). -#}
select
  vintage_year,
  split,
  count(*)                              as loans,
  sum(default_24m)                      as defaults,
  round(100.0 * avg(default_24m), 2)    as default_rate_pct
from {{ ref('mart_loan_features') }}
group by vintage_year, split
order by vintage_year, split
