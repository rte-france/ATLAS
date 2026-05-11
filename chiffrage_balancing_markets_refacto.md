# Chiffrage — Refacto Balancing Markets Orders

## Périmètre

- `balancing_market_bsp_orders` (~4 200 lignes)
- `balancing_market_tso_orders` (~7 000 lignes, dont un fichier de 3 768 lignes)

---

## 1. Migration vers l'API ATLAS

### Module BSP

| Tâche | Contenu | Estimation |
|---|---|---|
| Architecture & structure | `module.py`, `parameters.py` (Pydantic, 14 params), `dataset.py`, `input_objects/` par type équipement | 2j |
| Formulations simples | `load.py` (223 l.) + `wind_pv.py` (265 l.) — typage complet, AtlasDataset, pendulum | 2, 5j |
| Formulations complexes | `hydraulic.py` (367 l.) + `storage.py` (403 l.) — reservoir / energy constraints | 3j |
| Formulation thermique | `thermal.py` (1 397 l.) — le plus dense du module, typage complet | 4.5j |
| Contraintes dynamiques | `dynamic_constraints_functions.py` (837 l.) — migration + découpage en sous-fichiers thématiques | 3.5j |
| Refactor opportuniste |  | 1j |
| **Total BSP** | | **~16.5j** |

### Module TSO

| Tâche | Contenu | Estimation |
|---|---|---|
| Architecture & structure | `module.py`, `parameters.py` (Pydantic, 20+ params, `AlternativeType` → enum), `dataset.py`, `input_objects/` | 2j |
| `main.py` + Pricings | `main.py` (319 l.) → `module.execute()` + `need_slices_creation.py`, `FrBM_alt_pricing.py`, `mfrr_alt_pricing.py` (~1 230 l. total) | 4.5j |
| Simulations FrBM | `frbm_simulations_main.py` (389 l.) + `OptimizationFiles/` hors thermique (605 l.) — interface `OptimisationModel`. **Dépend du refacto Optimal Dispatch** (`ThermalDispatch`, `StorageDispatch`, `HydroDispatch` dans common) : si disponible, la physique des équipements est réutilisée et l'effort tombe à ~2j. | 4.5j _(~2j si post-OD)_ |
| Contraintes dynamiques thermiques | `thermal_dynamic_constraints.py` (3 768 l.) — **risque principal**, migration + découpage obligatoire en sous-fichiers. **Dépend du refacto Optimal Dispatch** : `ThermalDispatch` absorbe la physique, seules les contraintes TSO-spécifiques restent — tombe à ~2j. | 8j _(~2j si post-OD)_ |
| Refactor opportuniste | Split fichier 3 768 l. — **trivial si post-OD** : `ThermalDispatch` rend le découpage naturel, plus de monolithe à splitter. | 1j _(~0j si post-OD)_ |
| **Total TSO** | | **~20j** _(~11j si post-OD)_ |

**Sous-total migration : ~36.5j** _(~30j si post-OD)_

---

## 2. Testing / CI-CD / Validation

### Module BSP

| Tâche | Contenu | Estimation |
|---|---|---|
| Dataset de test | Fixtures : marker minimal, équipements par technologie (5 types), cas limites | 1.5j |
| Tests unitaires | Contraintes dynamiques, formulation helpers | 2j |
| Tests module | Thermal (gradient, MSP, PHS) + hydraulique/stockage + RES/load — couverture par type | 3.5j |
| Tests intégration + CI | Run bout-en-bout, marqueur `@pytest.mark.integration` | 1.5j |
| **Total BSP** | | **~8.5j** |

### Module TSO

| Tâche | Contenu | Estimation |
|---|---|---|
| Dataset de test | Fixtures : ControlBlocks, needs, stacks de pricing | 1.5j |
| Tests unitaires | Pricing helpers, slices, needs computation | 2j |
| Tests module | FrBM (simulation + slices), mFRR, at-all-costs — couverture par `AlternativeType` | 3.5j |
| Tests intégration + CI | Run bout-en-bout| 1.5j |
| **Total TSO** | | **~8.5j** |

**Sous-total testing : ~17j**

---

## 3. Documentation statique

| Tâche | Contenu | Estimation |
|---|---|---|
| Docstrings BSP | Format Sphinx, classes + fonctions publiques (formulations, contraintes) | 1.5j |
| Docstrings TSO | Idem + pricing strategies + FrBM (plus riche) | 2j |
| Pages | Une page par module : paramètres, workflow, types d'entrées/sorties | 1j |
| **Total doc** | | **~4.5j** |

---

## Récapitulatif

| Axe | BSP | TSO | Total |
|---|---|---|---|
| Migration API ATLAS | 16.5j | 20j | **36.5j** |
| Migration API ATLAS _(si post-OD)_ | 16.5j | ~11j | **~27.5j** |
| Testing / CI-CD | 8.5j | 8.5j | **17j** |
| Documentation statique | 2.5j | 2.5j | **5j** |
| **Total par module** | **27.5j** | **31j** | **~58.5j** |
| **Total par module _(si post-OD)_** | **27.5j** | **~22j** | **~49.5j** |

---
