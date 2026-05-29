# LP changes — optimal dispatch migration

Comparaison des LPs avant/après l'introduction de `ThermalDispatch`, `ThermalReserveHandler`, `StorageDispatch` dans `atlas/common/optimal_dispatch/`.  
Scope : Day-Ahead Orders (DAO) et Portfolio Optimisation (PO) — stockage et thermique.

| | Thermique DAO | Stockage DAO |
|---|---|---|
| **Nommage variables** | `prefix_equip_{n}_at_{t}` → `{type}_{n}_{t}` | `Amount_sold/purchased` → `power_level_sell/buy` |
| **Convention signe** | inchangée | `power_level_buy ≤ 0` (était `Amount_purchased ≥ 0`) |
| **Nommage contraintes** | `constraint_N` générique → noms sémantiques | idem |
| **Taille LP** | **+72 à +327 lignes** selon features (section Binaries) | **−38 %** (contraintes absorbées dans Bounds) |
| **Maths** | Identique — sauf deux correctifs (voir §Thermique) | Identique |
| **PO** | Δ = 0 (déjà migré avant la baseline DAO) | — |

---

## Thermique

### Nommage variables et contraintes

```
\ Avant
power_equip_fr_fr_nuclear_cp0_cp1_cp2_at_2028_09_27_00_00_00_00_00
OFF_equip_fr_fr_nuclear_cp0_cp1_cp2_at_2028_09_27_00_00_00_00_00
constraint_0: +1 OFF_equip_... +1 turned_on_equip_...  <= 1
constraint_1: +1 turned_on_equip_...  <= 0

\ Après
fr_fr_nuclear_cp0_cp1_cp2_power_level_2028_09_27_00_00_00_00_00
off_fr_fr_nuclear_cp0_cp1_cp2_2028_09_27_00_00_00_00_00
t_on_evol_1_2028_09_27_00_00_00_00_00_fr_fr_nuclear_cp0_cp1_cp2:
    +1 off_... +1 t_on_...  <= 1
mutual_exclusion_2028_09_27_...: +1 off_... +1 on_up_... +1 on_down_...  = 1
```

Même structure, noms sémantiques partagés entre DAO et PO.

### Déclaration binaire des variables d'état

`turned_on` et `turned_off` étaient déclarées **continues `[0,1]`** dans l'ancien LP (absentes de la section `Binaries`). `ThermalDispatch` les renomme `t_on`/`t_off` et les déclare binaires.

Note OR-Tools : l'exporteur liste les binaires dans `Bounds` **et** dans `Binaries` (redondance intentionnelle de `MPModelProtoExporter`). La section `Bounds` ne change donc pas de taille — seule `Binaries` grandit.

### Variations par combinaison (36 ts, 1 unité)

| Combo | Features | Δ lignes | Binaires ajoutées dans `Binaries` |
|---|---|---|---|
| 1 | base (off/on_up/on_down) | **+72** | `t_on`(36) `t_off`(36) |
| 4 | + START | **+72** | `t_on` `t_off` (`on_start` existait déjà) |
| 2 | + STOP | **+108** | `t_on` `t_off` `down_to_stop_grad`(36) |
| 7 | + START + STOP | **+108** | `t_on` `t_off` `down_to_stop_grad` |
| 3 | + ON_FLAT | **+146** | `t_on` `t_off` `entered_up`(37) `entered_down`(37) `stable`(37) |
| 6 | + ON_FLAT + START | **+183** | idem combo-3 + `on_start` |
| 5 | + ON_FLAT + STOP | **+291** | idem combo-3 + `down_to_stop_grad` `flat_down_stop` |
| 8 | + ON_FLAT + START + STOP | **+327** | cumul de tout |

`entered_up`, `entered_down`, `stable`, `down_to_stop_grad`, `flat_down_stop` sont des **variables entièrement nouvelles** (absentes de l'ancien LP) introduites pour modéliser explicitement les transitions d'état ON_FLAT et la rampe d'arrêt.

#### Réduction de contraintes dans combo-3 (−37)

Combo-3 perd 37 contraintes (`minimum_time_on_` −36, `minimum_time_stable_` −1) car l'ancien code itérait sur `time_frame_union_minus_one` (37 ts = `time_frame` + `start_date − 1h`), alors que `ThermalDispatch` itère sur `time_frame` (36 ts). Pour les combos avec START/STOP, un passage spécial à `time == start_date` compense — combo-3 (ON_FLAT seul) ne le déclenche pas, d'où le delta.

Ces 37 contraintes sont redondantes : `turned_on(start_date − s·h)` est une constante fixée via `ModelVar.set_extended`, et la somme `on_up + on_down + on_flat` à `start_date − 1h` est épinglée à `1 − off_fixé` par la contrainte `mutual_exclusion` existante. Leur suppression est neutre.

### Impact mathématique

| Changement | Effet sur la solution |
|---|---|
| Renommage variables/contraintes | Neutre |
| `t_on`/`t_off` continu → binaire | Neutre si la relaxation LP était déjà entière¹ ; sinon correctif |
| `entered_up`, `stable`, etc. (variables auxiliaires) | Neutre sur la projection² ; peut affiner la modélisation du palier stable |
| Suppression des 37 contraintes pré-horizon | Neutre (redondantes, voir ci-dessus) |

¹ *Relaxation LP* : OR-Tools résout d'abord le problème en traitant tous les binaires comme des continus `[0,1]`. Si cette relaxation est déjà entière, déclarer des variables binaires ne change pas l'optimum.  
² *Projection* : une variable auxiliaire entièrement déterminée par des contraintes de définition ne modifie pas l'espace réalisable exprimé sur les variables originales.

### PO thermique

Δ = 0 — le PO avait été migré vers `ThermalDispatch` dans le commit `684e8fd5`, antérieur à la baseline DAO `032dbb69`.

---

## Stockage DAO

### Variables et convention de signe

| Avant | Après | Raison |
|---|---|---|
| `Amount_sold_at_{t}` | `{unit}_power_level_sell_{t}` | nommage cohérent multi-module |
| `Amount_purchased_at_{t}` | `{unit}_power_level_buy_{t}` | id. + signe inversé |
| `isSell_at_{t}` | `{unit}_is_sell_{t}` | id. |
| `StoredEnergy_at_{t}` | `{unit}_stored_energy_{t}` | id. |
| `Amount_sold_in_fragment_{i}_at_{t}` | `{unit}_power_level_sell_n_{i}_{t}` | alignement PO |
| `Amount_purchased_in_fragment_{i}_at_{t}` | `{unit}_power_level_buy_n_{i}_{t}` | id. + signe inversé |

`Amount_purchased ≥ 0` → `power_level_buy ≤ 0` : relation `power_level_buy = −Amount_purchased`. L'inversion unifie la convention avec le PO et permet de partager `StorageDispatch`.

### Section Bounds — contraintes absorbées

```
\ Avant : bornes libres, contraintes explicites dans Subject To
 0 <= StoredEnergy_at_{t}
 Minimum_storage_level_constraint_at_{t}: +1 StoredEnergy_at_{t}  >= 2000
 Maximum_storage_level_constraint_at_{t}: +1 StoredEnergy_at_{t}  <= 10000
 Respect_Pmin_sale_at_{t}: +1 Amount_sold_at_{t}  >= 0
 Respect_of_sale_power_fragment_{i}_limit_at_{t}: +3 Amount_sold_in_fragment_{i}_{t}  <= 4000

\ Après : bornes serrées, contraintes supprimées
 0 <= a_battery_1_power_level_sell_{t} <= 4000
 -4000 <= a_battery_1_power_level_buy_{t} <= 0
 2000 <= a_battery_1_stored_energy_{t} <= 10000
 0 <= a_battery_1_power_level_sell_n_0_{t} <= 1333.33
 -1333.33 <= a_battery_1_power_level_buy_n_0_{t} <= 0
```

Sur 48 h, 3 fragments : **480 contraintes supprimées** → −38 % de lignes. OR-Tools traite les bornes en presolve sans les injecter dans la matrice.

### Contraintes — changements clés

**Suivi de stock** — seul le signe du terme achat change (inversion de convention) :
```
\ Avant :  +1.11111 Amount_sold  -0.9 Amount_purchased  +1 StoredEnergy  = 6000
\ Après :  +1.11111 power_level_sell  +0.9 power_level_buy  +1 stored_energy  = 6000
```

**Séparation vente/achat** — contrainte d'achat reformulée à signe équivalent :
```
\ Avant :  +1 Amount_purchased  +4000 isSell  <= 4000   (Amount_purchased ≥ 0)
\ Après :  -1 power_level_buy   +4000 is_sell <= 4000   (power_level_buy ≤ 0)
```

**Sommation fragments** et **objectif** — structure identique, signe buy cohérent dans les deux cas.

### Impact taille (DAO, 48 h, 3 fragments)

| Fichier | Avant | Après | Delta |
|---|---|---|---|
| `storage_a_battery_1.lp` | 1 889 lignes | 1 169 lignes | **−38 %** |
| `storage_a_electric_vehicle_1.lp` | 1 264 lignes | 785 lignes | **−38 %** |

---

## Stockage PO

Mêmes `StorageDispatch` et `StorageReserveHandler` qu'en DAO. Différences PO : ajout des variables de réserves (`StorageReserveHandler`) et remplacement de la contrainte de cycle balance par une contrainte de fill-up réserves.
