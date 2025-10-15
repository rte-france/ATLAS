# Validation

## Variables

- `es_hydro_stored_energy_2028_09_27_00_00_00_00_00` , `es_phs_stored_energy_2028_10_01_06_00_00_00_00`-> petite différence de 2

- `generator_es_small_imbalance_down/up` -> tout est dans le calcul du `max_power` * `small_imbalance_size` = `small_imbalance_limit` j'ai rechecké, le calcul du max_power, c'est bien la somme sur tout le portfolio des maximum_power de chaque équipment, je vois pas de différence ! *Le premier pas de temps* j'ai bien la bonne valeur 


## Objective

- J'ai une inversion de signe sur les `power_level_sell` & `power_level_buy` des différents type de storage, chose que je n'ai pas sur la meme chose avec les fragments n = 0..
- j'ai une difference donc sur les fragments suivants, la différence est d'un facteur constant pour chaque n
- j'ai un facteur constant qui s'applique et qui explique la différence sur les coefficients de `generator_es_small_imbalance_down` et `generator_es_small_imbalance_up` de l'ordre de 1.05 

## Contraintes 

Aucun naming initialement, je peux pas comparer


