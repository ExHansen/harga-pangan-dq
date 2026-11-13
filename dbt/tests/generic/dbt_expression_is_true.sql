{% test dbt_expression_is_true(model, expression) %}
-- Rows for which the boolean expression is not true.
select *
from {{ model }}
where not ({{ expression }})
{% endtest %}
