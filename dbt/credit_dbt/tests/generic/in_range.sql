{#- Fails for every row whose value is present but outside [min_value, max_value]. NULL is allowed (use not_null to forbid it). -#}
{% test in_range(model, column_name, min_value, max_value) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
  and ({{ column_name }} < {{ min_value }} or {{ column_name }} > {{ max_value }})
{% endtest %}
