{#- Same idea for the two staging tables: identical to the Parquet files of credit/freddie/staging.py. -#}
with orig_mine as (select * from {{ ref('stg_orig') }}),
orig_theirs as (select * from read_parquet('{{ var("existing_stg_dir") }}/stg_orig_*.parquet', union_by_name = true)),
label_mine as (select * from {{ ref('stg_label') }}),
label_theirs as (select * from read_parquet('{{ var("existing_stg_dir") }}/stg_label_*.parquet', union_by_name = true))
select 'stg_orig only in dbt' as problem, count(*) as n from (select * from orig_mine except select * from orig_theirs) having count(*) > 0
union all
select 'stg_orig only in the existing pipeline', count(*) from (select * from orig_theirs except select * from orig_mine) having count(*) > 0
union all
select 'stg_label only in dbt', count(*) from (select * from label_mine except select * from label_theirs) having count(*) > 0
union all
select 'stg_label only in the existing pipeline', count(*) from (select * from label_theirs except select * from label_mine) having count(*) > 0
