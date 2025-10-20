# Validation

## Variables

- `es_hydro_stored_energy_2028_09_27_00_00_00_00_00` , `es_phs_stored_energy_2028_10_01_06_00_00_00_00`-> petite différence de 2, on accepte ou pas ?

- `generator_es_small_imbalance_down/up` -> tout est dans le calcul du `max_power` * `small_imbalance_size` = `small_imbalance_limit` j'ai rechecké, le calcul du max_power, c'est bien la somme sur tout le portfolio des maximum_power de chaque équipment, je vois pas de différence ! *Le premier pas de temps* j'ai bien la bonne valeur


## Objective


- j'ai un facteur constant qui s'applique et qui explique la différence sur les coefficients de `generator_es_small_imbalance_down` et `generator_es_small_imbalance_up` de l'ordre de 1.05

## Contraintes

Aucun naming initialement, je peux pas comparer
