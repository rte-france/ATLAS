import polars as pl

import atlas.config as cfg
from atlas.io_utils.input_loader import InputLoader
from atlas.modules.portfolio_optimisation.module import PortfolioOptimisationModule
from atlas.solver.solver_helper import SolverHelper
from atlas.timing import timer

MAPPING = {
    "Power_level": "power_level",
    "_at_": "_",
    "Stored_energy": "stored_energy",
    "StoredEnergy": "stored_energy",
    "large_imbal_down": "large_imbalance_down_",
    "large_imbal_up": "large_imbalance_up_",
    "small_imbal_down": "small_imbalance_down_",
    "small_imbal_up": "small_imbalance_up_",
    "resDown_e": "reserves_down",
    "resUp_e": "reserves_up",
    "ressUp_e": "reserves_up",
    "unprResDown_e": "unprovided_reserves_down",
    "unprResUp_e": "unprovided_reserves_up",
    "autoContractedDiffDown_e": "automated_contracted_diff_down",
    "autoContractedDiffUp_e": "automated_contracted_diff_up",
    "contractedDiffDown_e": "contracted_diff_down",
    "contractedDiffUp_e": "contracted_diff_up",
    "autoResDown_e": "automated_reserves_down",
    "autoResUp_e": "automated_reserves_up",
}


def replace_patterns_in_column(filename: str, df: pl.DataFrame):
    df = pl.read_csv(filename, separator=";")

    df_mapped = df.clone()

    for old_pattern, new_pattern in MAPPING.items():
        df_mapped = df_mapped.with_columns(
            pl.col("Original Name").str.replace_all(old_pattern, new_pattern).alias("Original Name")
        )

    df_mapped.write_csv(filename, separator=";")


if __name__ == "__main__":
    module = PortfolioOptimisationModule()

    with timer() as t:
        raw_data = InputLoader.from_directory("data/atlas-dataset/portfolio-optimisation", lazy=False)
    cfg.logger.info(f"{t()} to load data")
    with timer() as t:
        try:
            module.run(raw_data=raw_data, raw_params="parameters.yaml")
        except Exception:
            cfg.logger.info(f"{t()} to run module")

    replace_patterns_in_column("Portfolio_generator_es.lp_correspondance.csv")

    SolverHelper.rebuild_lp_with_real_names("po.lp", "Portfolio_generator_es.lp_correspondance.csv", "po_renamed.lp")
    atlas_lp = SolverHelper.read_lp_ortools("po.lp")
    legacy_lp = SolverHelper.read_lp_legacy("po_legacy.lp")
    contraints, variables, objective = SolverHelper.compare_lp_problems(atlas_lp, legacy_lp)
