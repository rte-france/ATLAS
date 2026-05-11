# Chiffrage — Refacto Optimal Dispatch

---

## Vue d'ensemble

| Phase | Description | Effort | Cumulé |
|---|---|---|---|
| **0** | Fondation common (squelette + Pydantic) | ~2j | ~2j |
| **1** | Thermal commun (extraction + bascule PO + bascule DA) | ~1 sem. | ~1.5 sem. |
| **2** | Storage commun (extraction + bascule PO + bascule DA) | ~1 sem. | ~2.5 sem. |
| **3** | Migration heuristiques DA → optim (par techno) | ~2.5 sem. | ~5 sem. |
| **4** | DA portfolio-based _(optionnel, à valider métier)_ | ~2 sem. | ~7 sem. |

**MVP de convergence (phases 0+1+2) : ~2.5 semaines**
**Full refacto hors phase 4 : ~5 semaines**
**Full refacto avec phase 4 : ~7 semaines**

---

## Phase 0 — Fondation common `~2 jours`

| # | Description | Effort |
|---|---|---|
| 1 | Créer `atlas/common/optimal_dispatch/{pydantic,dispatch,initial_conditions}/__init__.py` — pure arborescence | 0.5j |
| 2 | `ThermalDispatchInput` : identifier les champs physiques (pas DA-only, pas PO-only), écrire le contrat, tests d'instanciation | 0.5j |
| 3 | `StorageDispatchInput` : idem + sous-types Battery/EV/PHS | 0.5j |
| 4 | `ThermalDAO`/`ThermalPO` héritent de `ThermalDispatchInput` : changer la classe parente, vérifier tests inchangés. Idem Storage. | 0.5j |

**Sortie** : arborescence en place, contrats Pydantic définis, tests existants inchangés.

---

## Phase 1 — Thermal commun `~1 semaine`

Le plus complexe du refacto : 8 combinaisons d'états, gradients, initial conditions gérées inline côté DA (vs factorisées côté PO).

### Étape 1.1 — Extraction depuis PO

| # | Description | Effort |
|---|---|---|
| 5 | Copier `initial_conditions_utils.py` PO → common, adapter imports | 0.5j |
| 6 | Extraire `ThermalDispatch` (893L) — garder physique pure, retirer réserves et objectif. Tests unitaires sur les contraintes. | 1.5j |
| 7 | `ThermalPOStep` compose `ThermalDispatch` + `ThermalReserves`. LP parity test. | 1j |
| 8 | Supprimer `constraint_builder.py` PO. Zéro import résiduel. | 0.5j |

### Étape 1.2 — Bascule DA

| # | Description | Effort |
|---|---|---|
| 9 | `thermal_optimization_model.py` (627L → ~150L) — initial conditions inline à refactoriser. LP parity test DA. | 1j |
| 10 | Supprimer `constraint_builder.py` DA (946L), zéro import résiduel. | 0.5j |
| 11 | Réorganiser `orders_strategies/{base_load,intermediate,peak,unit}.py` — chacune consomme `ThermalDispatch` via accesseurs publics. | 0.5j |

**Sortie** : `common.ThermalDispatch` source unique de vérité pour la physique thermique. ~1500 lignes de duplication éliminées.

---

## Phase 2 — Storage commun `~1 semaine`

Même pattern que phase 1, complexité moindre grâce au template établi.

| # | Description | Effort |
|---|---|---|
| 12 | Copier initial conditions storage → common (si applicable) | 0.5j |
| 13 | Extraire `StorageDispatch` : approche paramétrée par sous-type, logique EV dans `_add_ev_constraints()`. Tests unitaires. | 1.5j |
| 14 | `StorageDispatch` + `StorageReserves` dans PO. LP parity PO. | 0.5j |
| 15 | Remplacer `BatteryModel` / `ElectricVehicleModel` / `StorageModel` → `StorageDispatch` dans DA. LP parity DA. | 1j |
| 16 | Supprimer `day_ahead_orders/steps/storage/optim/{storage,battery,ev}.py` (469L) | 0.5j |

**Sortie** : storage unifié. ~700 lignes éliminées. Pattern validé sur 2 technos.

---

## Phase 3 — Migration heuristiques DA → optim `~2.5 semaines`

Branches indépendantes, parallélisables. Pattern fixé par phases 1+2.

| Techno | Complexité | Effort |
|---|---|---|
| **Hydro** | SoC + fragments — proche storage, pas de sous-types | ~4j |
| **Solar** | Curtailment uniquement — trivial | ~2j |
| **Wind** | Idem Solar | ~2j |
| **Load** | Pas de modèle PO existant à extraire — création `LoadDispatch` from scratch | ~1 sem. |
| **Non-dispatchable** | Cas à évaluer, probablement minimal | ~2j |

**Total : ~2.5 semaines** (en parallèle : ~1 semaine avec deux devs)

---

## Phase 4 — DA portfolio-based `~2 semaines` _(optionnel)_

**Prérequis** : phase 3 terminée + validation métier (un ordre par équipement reste-t-il pertinent en mode portfolio ?).

| Travail | Effort |
|---|---|
| Réutiliser l'orchestrateur PO (`run_parallel` / `ProcessPoolExecutor`) côté DA | ~3j |
| Agréger les équipements DA en portfolios, solve par portfolio | ~4j |
| Post-traitement : ventiler la solution portfolio en ordres par équipement | ~3j |

---

## Stratégie de tests (transverse)

**LP parity** — obligatoire avant chaque bascule : exporter le `.lp` avant/après commit, diff strict sur les contraintes physiques. Fixtures dans `tests/test_module/test_{day_ahead_orders,portfolio_optimisation}/lp_files/thermal/`.

**Tests unitaires** sur les contraintes communes : `tests/common/optimal_dispatch/` — 1 équipement, 2-3 timesteps, vérifier coefficients. Couvrir les 8 combinaisons thermiques.

**Tests d'intégration** existants : doivent passer inchangés après chaque phase. Un test qui casse = régression réelle.

---
