{#- The table the models learn from. Same steps as build() in credit/freddie/features.py:
    join, drop relief refinances / seasoned loans / loans not watched for 24 months, add rate_spread, add the split.
    The split is a hash of loan_seq, so it is reproducible and never changes when data is added. -#}
with joined as (
  select o.*, l.observable_24m, l.default_24m, l.default_24m_all_late, l.default_24m_loss_only
  from {{ ref('stg_orig') }} o
  join {{ ref('stg_label') }} l using (loan_seq)
),
kept as (
  select * from joined
  where not relief_refi and not is_seasoned_or_modified and observable_24m
),
spread as (
  -- this loan's rate minus the median rate of the kept loans of the same vintage quarter and term class (inputs only, never outcomes)
  select *,
    int_rate - quantile_cont(int_rate, 0.5)
      over (partition by vintage_year, vintage_quarter, (orig_term > {{ var('short_term_months') }})) as rate_spread
  from kept
)
select
  {{ feature_columns() }},
  case
    when vintage_year <= {{ var('dev_max_vintage') }} then
      case
        when hash(loan_seq || '{{ var("split_seed") }}') % 100 < 60 then 'train'
        when hash(loan_seq || '{{ var("split_seed") }}') % 100 < 70 then 'calibration'
        when hash(loan_seq || '{{ var("split_seed") }}') % 100 < 85 then 'validation'
        else 'test_in_time'
      end
    when vintage_year between {{ var('oot_1_min') }} and {{ var('oot_1_max') }} then 'test_oot_2019'
    when vintage_year >= {{ var('oot_2_min') }} then 'test_oot_2022'
  end as split
from spread
