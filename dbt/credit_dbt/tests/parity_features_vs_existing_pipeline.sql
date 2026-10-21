{#- "Test your work instead of assuming it is right": the dbt table must be identical to the one the existing pipeline
    wrote (data/interim/features/features.parquet). Any row that exists on one side only makes the test fail. -#}
with mine as (
  select {{ feature_columns() }}, split from {{ ref('mart_loan_features') }}
),
theirs as (
  select {{ feature_columns() }}, split from read_parquet('{{ var("existing_features") }}')
)
select 'only in dbt' as side, * from (select * from mine except select * from theirs)
union all
select 'only in the existing pipeline' as side, * from (select * from theirs except select * from mine)
