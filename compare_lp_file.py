import re
from pathlib import Path

import polars as pl

from atlas.solver.solver_helper import SolverHelper

MAPPING = {
    "Power_level": "power_level",
    "_at_": "_",
    "Stored_energy": "stored_energy",
    "Stored_Energy": "stored_energy",
    "StoredEnergy": "stored_energy",
    "large_imbal_down": "large_imbalance_down",
    "large_imbal_up": "large_imbalance_up",
    "small_imbal_down": "small_imbalance_down",
    "small_imbal_up": "small_imbalance_up",
    "resDown_e": "reserves_down",
    "resUp_e": "reserves_up",
    "ressUp_e": "reserves_up",
    "relRes_e": "relaxed_reserves",
    "unprResDown_e": "unprovided_reserves_down",
    "unprResUp_e": "unprovided_reserves_up",
    "autoContractedDiffDown_e": "automated_contracted_diff_down",
    "autoContractedDiffUp_e": "automated_contracted_diff_up",
    "contractedDiffDown_e": "contracted_diff_down",
    "contractedDiffUp_e": "contracted_diff_up",
    "autoResDown_e": "automated_reserves_down",
    "autoResUp_e": "automated_reserves_up",
}


def convert_date_format_in_csv(filename: str):
    """
    Convert date format in CSV from day_month_year to year_month_day and replace colons with underscores
    Pattern: DD_MM_YYYY becomes YYYY_MM_DD
    Also replaces any ':' with '_' (useful for time components like HH:MM:SS -> HH_MM_SS)
    """
    df = pl.read_csv(filename, separator=";")

    def convert_date_pattern(text: str) -> str:
        """Convert date pattern from DD_MM_YYYY to YYYY_MM_DD and replace : with _"""
        # Pattern to match DD_MM_YYYY format (2 digits day, 2 digits month, 4 digits year)
        pattern = r"(\d{2})_(\d{2})_(\d{4})"

        def replace_match(match):
            day, month, year = match.groups()
            return f"{year}_{month}_{day}"

        # First convert date format
        result = re.sub(pattern, replace_match, text)

        # Then replace any colons with underscores (for time components)
        result = result.replace(":", "_")

        return result

    # Apply the conversion to the "Original Name" column
    df_converted = df.with_columns(
        pl.col("Original Name").map_elements(convert_date_pattern, return_dtype=pl.Utf8).alias("Original Name")
    )

    # Write back to the same file
    df_converted.write_csv(filename, separator=";")
    print(f"Date format conversion completed for {filename}")


def replace_patterns_in_column(filename: str):
    df = pl.read_csv(filename, separator=";")

    df_mapped = df.clone()

    for old_pattern, new_pattern in MAPPING.items():
        df_mapped = df_mapped.with_columns(
            pl.col("Original Name").str.replace_all(old_pattern, new_pattern).alias("Original Name")
        )

    df_mapped = df_mapped.with_columns(
        pl.when(pl.col("Type") == "variable Constraints")
        .then(pl.col("Original Name") + "_00_00")
        .otherwise(pl.col("Original Name"))
        .alias("Original Name")
    ).with_columns(
        pl.when(pl.col("Type") == "variable Binaries")
        .then(pl.col("Original Name") + "_00_00")
        .otherwise(pl.col("Original Name"))
        .alias("Original Name")
    )

    df_mapped.write_csv(filename, separator=";")


if __name__ == "__main__":
    # module = PortfolioOptimisationModule()

    # with timer() as t:
    #     raw_data = InputLoader.from_directory("data/atlas-dataset/portfolio-optimisation", lazy=False)
    # cfg.logger.info(f"{t()} to load data")
    # with timer() as t:
    #     try:
    #         module.run(raw_data=raw_data, raw_params="parameters.yaml")
    #     except Exception:
    #         cfg.logger.info(f"{t()} to run module")

    # Convert date format from day_month_year to year_month_day
    # convert_date_format_in_csv("Portfolio_generator_es.lp_correspondance.csv")

    # replace_patterns_in_column("Portfolio_generator_es.lp_correspondance.csv")

    SolverHelper.rebuild_lp_with_real_names(
        "po_legacy.lp", "Portfolio_generator_es.lp_correspondance.csv", "po_renamed.lp"
    )
    atlas_lp = SolverHelper.read_lp_ortools("po_generator_es.lp")
    legacy_lp = SolverHelper.read_lp_legacy("po_renamed.lp")

    # Use the new merged comparison method that exports CSV files and generates summary report
    print("Comparing LP problems and generating comprehensive report...")
    output_dir = Path("lp_comparison_results")
    output_dir.mkdir(exist_ok=True)

    summary = SolverHelper.compare_lp_problems(
        legacy_lp, atlas_lp, output_dir=output_dir, pb1_name="Legacy_LP", pb2_name="Atlas_LP", tolerance=1e-1
    )
