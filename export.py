from atlas.io_utils.input_loader import InputLoader
from atlas.io_utils.prometheus_transformer import PrometheusToAtlasDataParser

timeseries_folder_path = "data/po_timeseries"
hdf5_path = "data/d4683492-e815-4021-a2cf-516c2825efcc"
output_dir = "data/atlas-dataset/portfolio-optimisation"

transformer = PrometheusToAtlasDataParser(
    timeseries_path=timeseries_folder_path,
    hdf5_path=hdf5_path,
    root_input_directory=output_dir,
)
transformer.process()

raw_data = InputLoader.from_directory(output_dir, lazy=False)
