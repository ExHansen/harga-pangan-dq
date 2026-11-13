{% test unique_combination(model, combination) %}
-- Rows whose combination of columns is not unique (the grain of the model is broken).
select {{ combination | join(', ') }}, count(*) as n_rows
from {{ model }}
group by {{ combination | join(', ') }}
having count(*) > 1
{% endtest %}
