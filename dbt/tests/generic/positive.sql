{% test positive(model, column_name) %}
-- Values that are zero or negative (nulls are left to not_null).
select {{ column_name }}
from {{ model }}
where {{ column_name }} <= 0
{% endtest %}
