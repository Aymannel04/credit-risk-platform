{#- The fresh vintages too: staging tables and the features table must equal what the existing pipeline wrote. -#}
with feat_mine as (select {{ fresh_feature_columns() }}, split from {{ ref('mart_loan_features_fresh') }}),
feat_theirs as (select {{ fresh_feature_columns() }}, split from read_parquet('{{ var("existing_features_fresh") }}')),
orig_mine as (select * from {{ ref('stg_orig_fresh') }}),
orig_theirs as (select * from read_parquet('{{ var("existing_stg_fresh_dir") }}/stg_orig_*.parquet', union_by_name = true)),
label_mine as (select * from {{ ref('stg_label_fresh') }}),
label_theirs as (select * from read_parquet('{{ var("existing_stg_fresh_dir") }}/stg_label_*.parquet', union_by_name = true))
select 'features only in dbt' as problem, count(*) as n from (select * from feat_mine except select * from feat_theirs) having count(*) > 0
union all
select 'features only in the existing pipeline', count(*) from (select * from feat_theirs except select * from feat_mine) having count(*) > 0
union all
select 'stg_orig only in dbt', count(*) from (select * from orig_mine except select * from orig_theirs) having count(*) > 0
union all
select 'stg_orig only in the existing pipeline', count(*) from (select * from orig_theirs except select * from orig_mine) having count(*) > 0
union all
select 'stg_label only in dbt', count(*) from (select * from label_mine except select * from label_theirs) having count(*) > 0
union all
select 'stg_label only in the existing pipeline', count(*) from (select * from label_theirs except select * from label_mine) having count(*) > 0
