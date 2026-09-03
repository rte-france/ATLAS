import pendulum

from atlas.io_utils.prometheus_transformer import PrometheusToAtlasDataParser


def _make_parser(tmp_path) -> PrometheusToAtlasDataParser:
    return PrometheusToAtlasDataParser(
        timeseries_path=tmp_path / "timeseries",
        hdf5_path=tmp_path / "data.hdf5",
        output_dir=tmp_path / "output",
        default_value=False,
    )


def test_read_and_parse_csv_infers_sparse_numeric_columns_across_full_file(tmp_path):
    # A forecasting matrix column whose first non-null value only appears after
    # row 100 must still be inferred as numeric, not silently typed as String
    # by polars' default 100-row schema inference sample.
    start = pendulum.datetime(2028, 1, 1)
    lines = ["TimeStep;01/07/2028 00:00:00;26/09/2028 15:00:00"]
    for i in range(150):
        timestep = start.add(hours=i).format("DD_MM_YYYY_HH_mm_ss")
        value = "-14739.57" if i == 149 else ""
        lines.append(f"{timestep};1.0;{value}")

    csv_file = tmp_path / "MaximumPowerForecast.csv"
    csv_file.write_text("\r\n".join(lines) + "\r\n")

    parser = _make_parser(tmp_path)
    df = parser._read_and_parse_csv(str(csv_file))

    assert df["26/09/2028 15:00:00"].dtype.is_numeric()
    assert df["26/09/2028 15:00:00"].drop_nulls().to_list() == [-14739.57]
