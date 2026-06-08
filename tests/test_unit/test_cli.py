"""Tests for the Atlas CLI application."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from atlas.app import app

runner = CliRunner()


class TestVersionCommand:
    """Tests for the 'atlas version' command."""

    def test_version_command_succeeds(self):
        """Test that the version command runs successfully."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "Atlas version" in result.stdout

    def test_version_output_format(self):
        """Test that the version output contains the expected format."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert ":" in result.stdout  # Format: "Atlas version : x.x.x"


class TestRunCommandModuleMode:
    """Tests for the 'atlas run' command in module mode."""

    def test_run_module_missing_module_flag(self, tmp_path):
        """Test that run fails when --module is missing in module mode."""
        params_file = tmp_path / "params.yaml"
        params_file.write_text("temporal:\n  start_date: '2028-09-27 00:00:00'")
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()

        result = runner.invoke(app, ["run", str(params_file), "--dataset", str(dataset_dir)])
        assert result.exit_code == 1
        assert "--module is required" in result.stdout

    def test_run_module_missing_dataset_flag(self, tmp_path):
        """Test that run fails when --dataset is missing in module mode."""
        params_file = tmp_path / "params.yaml"
        params_file.write_text("temporal:\n  start_date: '2028-09-27 00:00:00'")

        result = runner.invoke(app, ["run", str(params_file), "--module", "PortfolioOptimisation"])
        assert result.exit_code == 1
        assert "--dataset is required" in result.stdout

    def test_run_module_nonexistent_dataset(self, tmp_path):
        """Test that run fails when dataset directory doesn't exist."""
        params_file = tmp_path / "params.yaml"
        params_file.write_text("temporal:\n  start_date: '2028-09-27 00:00:00'")
        nonexistent_dir = tmp_path / "nonexistent"

        result = runner.invoke(
            app,
            ["run", str(params_file), "--module", "PortfolioOptimisation", "--dataset", str(nonexistent_dir)],
        )
        assert result.exit_code == 1
        assert "Dataset directory not found" in result.stdout

    def test_run_module_nonexistent_parameters(self, tmp_path):
        """Test that run fails when parameters file doesn't exist."""
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        nonexistent_params = tmp_path / "nonexistent.yaml"

        result = runner.invoke(
            app,
            ["run", str(nonexistent_params), "--module", "PortfolioOptimisation", "--dataset", str(dataset_dir)],
        )
        assert result.exit_code == 1
        assert "Parameters file not found" in result.stdout

    def test_run_module_invalid_module_name(self, tmp_path):
        """Test that run fails with an invalid module name."""
        params_file = tmp_path / "params.yaml"
        params_file.write_text("temporal:\n  start_date: '2028-09-27 00:00:00'")
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()

        result = runner.invoke(
            app,
            ["run", str(params_file), "--module", "InvalidModule", "--dataset", str(dataset_dir)],
        )
        assert result.exit_code == 1
        assert "Unknown module" in result.stdout

    @patch("atlas.app.ModuleRun")
    @patch("atlas.app.AtlasDataset")
    @patch("atlas.app.ModuleRegistry")
    def test_run_module_with_valid_inputs(self, mock_registry, mock_atlas_dataset, mock_module_run, tmp_path):
        """Test that run succeeds with valid inputs (mocked execution)."""
        # Setup mock module
        mock_module_class = MagicMock()
        mock_module_instance = MagicMock()
        mock_module_class.return_value = mock_module_instance
        mock_registry.get.return_value = mock_module_class

        # Setup mock parameters
        mock_params_class = MagicMock()
        mock_params_instance = MagicMock()
        mock_params_instance.output.export_output_dataset = False
        mock_params_class.from_file.return_value = mock_params_instance
        mock_module_instance.get_parameters_class.return_value = mock_params_class

        # Setup mock ModuleRun
        mock_run_instance = MagicMock()
        mock_module_run.return_value = mock_run_instance

        # Setup mock dataset loading
        mock_atlas_dataset.from_directory.return_value = MagicMock()

        # Create test files
        params_file = tmp_path / "params.yaml"
        params_file.write_text("temporal:\n  start_date: '2028-09-27 00:00:00'")
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()

        result = runner.invoke(
            app,
            ["run", str(params_file), "--module", "PortfolioOptimisation", "--dataset", str(dataset_dir)],
        )

        assert result.exit_code == 0
        assert "completed successfully" in result.stdout
        mock_registry.get.assert_called_once_with("PortfolioOptimisation")
        mock_module_run.assert_called_once()
        mock_run_instance.run.assert_called_once()


class TestRunCommandWorkflowMode:
    """Tests for the 'atlas run' command in workflow mode."""

    def test_run_workflow_nonexistent_config(self, tmp_path):
        """Test that run fails when workflow config doesn't exist."""
        nonexistent_config = tmp_path / "nonexistent_workflow.yaml"

        result = runner.invoke(app, ["run", str(nonexistent_config), "--workflow"])
        assert result.exit_code == 1
        assert "Workflow configuration file not found" in result.stdout

    @patch("atlas.app.Workflow")
    def test_run_workflow_with_valid_config(self, mock_workflow, tmp_path):
        """Test that run succeeds with valid workflow config (mocked execution)."""
        # Setup mock workflow
        mock_workflow_instance = MagicMock()
        mock_workflow.from_file.return_value = mock_workflow_instance

        # Create test workflow config
        workflow_config = tmp_path / "workflow.yaml"
        workflow_config.write_text(
            """
            dataset_path: ./dataset
            steps:
            - module: PortfolioOptimisation
                parameters_path: params.yaml
            """
        )

        result = runner.invoke(app, ["run", str(workflow_config), "--workflow"])

        assert result.exit_code == 0
        # Check that the workflow was executed (logs are printed, not in stdout)
        mock_workflow.from_file.assert_called_once()
        mock_workflow_instance.execute.assert_called_once()


class TestPrometheusToAtlasCommand:
    """Tests for the 'atlas prometheus-to-atlas' command."""

    def test_prometheus_to_atlas_missing_timeseries_folder(self, tmp_path):
        """Test that command fails when timeseries folder doesn't exist."""
        nonexistent_ts = tmp_path / "nonexistent_ts"
        hdf5_file = tmp_path / "data.hdf5"
        hdf5_file.write_text("")
        output_dir = tmp_path / "output"

        result = runner.invoke(
            app,
            ["prometheus-to-atlas", "run", str(nonexistent_ts), str(hdf5_file), "--output", str(output_dir)],
        )
        assert result.exit_code == 1
        assert "Timeseries folder not found" in result.stdout

    def test_prometheus_to_atlas_missing_hdf5_file(self, tmp_path):
        """Test that command fails when HDF5 file doesn't exist."""
        ts_folder = tmp_path / "ts"
        ts_folder.mkdir()
        nonexistent_hdf5 = tmp_path / "nonexistent.hdf5"
        output_dir = tmp_path / "output"

        result = runner.invoke(
            app,
            ["prometheus-to-atlas", "run", str(ts_folder), str(nonexistent_hdf5), "--output", str(output_dir)],
        )
        assert result.exit_code == 1
        assert "HDF5 file not found" in result.stdout

    @patch("atlas.app.PrometheusToAtlasDataParser")
    def test_prometheus_to_atlas_with_valid_inputs(self, mock_parser, tmp_path):
        """Test that command succeeds with valid inputs (mocked execution)."""
        # Create test files
        ts_folder = tmp_path / "ts"
        ts_folder.mkdir()
        hdf5_file = tmp_path / "data.hdf5"
        hdf5_file.write_text("")
        output_dir = tmp_path / "output"

        # Setup mock
        mock_parser_instance = MagicMock()
        mock_parser.return_value = mock_parser_instance

        result = runner.invoke(
            app,
            ["prometheus-to-atlas", "run", str(ts_folder), str(hdf5_file), "--output", str(output_dir)],
        )

        assert result.exit_code == 0
        mock_parser.assert_called_once()
        mock_parser_instance.process.assert_called_once()

    @patch("atlas.app.PrometheusToAtlasDataParser")
    def test_prometheus_to_atlas_with_custom_date_formats(self, mock_parser, tmp_path):
        """Test that command accepts custom date format parameters."""
        # Create test files
        ts_folder = tmp_path / "ts"
        ts_folder.mkdir()
        hdf5_file = tmp_path / "data.hdf5"
        hdf5_file.write_text("")
        output_dir = tmp_path / "output"

        # Setup mock
        mock_parser_instance = MagicMock()
        mock_parser.return_value = mock_parser_instance

        result = runner.invoke(
            app,
            [
                "prometheus-to-atlas",
                "run",
                str(ts_folder),
                str(hdf5_file),
                "--output",
                str(output_dir),
                "--date-format-forecasting",
                "YYYY-MM-DD",
                "--date-format-input-files",
                "YYYY-MM-DD",
                "--date-format-timestep",
                "YYYY_MM_DD",
            ],
        )

        assert result.exit_code == 0
        mock_parser.assert_called_once()


class TestPrometheusToAtlasRecursiveCommand:
    """Tests for the 'atlas prometheus-to-atlas-recursive' command."""

    def test_recursive_nonexistent_root_dir(self, tmp_path):
        """Test that command fails when root directory doesn't exist."""
        nonexistent_root = tmp_path / "nonexistent"
        output_root = tmp_path / "output"

        result = runner.invoke(
            app,
            ["prometheus-to-atlas", "batch", str(nonexistent_root), "--output", str(output_root)],
        )
        assert result.exit_code == 1
        assert "Root directory not found" in result.stdout

    def test_recursive_root_is_not_directory(self, tmp_path):
        """Test that command fails when root path is not a directory."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("")
        output_root = tmp_path / "output"

        result = runner.invoke(
            app,
            ["prometheus-to-atlas", "batch", str(file_path), "--output", str(output_root)],
        )
        assert result.exit_code == 1
        assert "Root directory not found" in result.stdout

    def test_recursive_no_valid_module_directories(self, tmp_path):
        """Test that command fails when no valid module directories are found."""
        root_dir = tmp_path / "root"
        root_dir.mkdir()
        # Create a directory without 'ts' folder
        (root_dir / "invalid_module").mkdir()
        output_root = tmp_path / "output"

        result = runner.invoke(
            app,
            ["prometheus-to-atlas", "batch", str(root_dir), "--output", str(output_root)],
        )
        assert result.exit_code == 1
        # Error message is logged, not printed to stdout

    @patch("atlas.app.find_hdf5_files")
    @patch("atlas.app.PrometheusToAtlasDataParser")
    def test_recursive_with_valid_module_directories(self, mock_parser, mock_find_hdf5, tmp_path):
        """Test that command processes valid module directories (mocked execution)."""
        # Create root directory with valid module structure
        root_dir = tmp_path / "root"
        root_dir.mkdir()

        module1_dir = root_dir / "module1"
        module1_dir.mkdir()
        (module1_dir / "ts").mkdir()
        hdf5_file1 = module1_dir / "data.hdf5"
        hdf5_file1.write_text("")

        module2_dir = root_dir / "module2"
        module2_dir.mkdir()
        (module2_dir / "ts").mkdir()
        hdf5_file2 = module2_dir / "data.hdf5"
        hdf5_file2.write_text("")

        output_root = tmp_path / "output"

        # Setup mocks
        mock_find_hdf5.side_effect = lambda x: [x / "data.hdf5"]
        mock_parser_instance = MagicMock()
        mock_parser.return_value = mock_parser_instance

        result = runner.invoke(
            app,
            ["prometheus-to-atlas", "batch", str(root_dir), "--output", str(output_root), "--no-mp"],
        )

        assert result.exit_code == 0
        # Both modules should have been processed
        assert mock_parser.call_count == 2

    @patch("atlas.app.find_hdf5_files")
    @patch("atlas.app.PrometheusToAtlasDataParser")
    def test_recursive_with_failed_module(self, mock_parser, mock_find_hdf5, tmp_path):
        """Test that command handles module processing failures gracefully."""
        # Create root directory with valid module structure
        root_dir = tmp_path / "root"
        root_dir.mkdir()

        module_dir = root_dir / "module1"
        module_dir.mkdir()
        (module_dir / "ts").mkdir()
        (module_dir / "data.hdf5").write_text("")

        output_root = tmp_path / "output"

        # Setup mocks to simulate failure
        mock_find_hdf5.side_effect = lambda x: [x / "data.hdf5"]
        mock_parser_instance = MagicMock()
        mock_parser_instance.process.side_effect = Exception("Test error")
        mock_parser.return_value = mock_parser_instance

        result = runner.invoke(
            app,
            ["prometheus-to-atlas", "batch", str(root_dir), "--output", str(output_root), "--no-mp"],
        )

        # Should exit with error code since no modules were processed
        assert result.exit_code == 1


class TestProfilingCommand:
    """Tests for the 'atlas profiling' command."""

    # --- Validation errors ---

    def test_profiling_invalid_level(self, tmp_path):
        params_file = tmp_path / "params.yaml"
        params_file.write_text("")
        result = runner.invoke(app, ["profiling", "--level", "invalid", "--parameters", str(params_file)])
        assert result.exit_code == 1
        assert "Unknown level" in result.stdout

    def test_profiling_nonexistent_parameters_file(self, tmp_path):
        nonexistent = tmp_path / "nonexistent.yaml"
        result = runner.invoke(app, ["profiling", "--level", "workflow", "--parameters", str(nonexistent)])
        assert result.exit_code == 1
        assert "Parameters file not found" in result.stdout

    def test_profiling_module_missing_module_flag(self, tmp_path):
        params_file = tmp_path / "params.yaml"
        params_file.write_text("")
        result = runner.invoke(app, ["profiling", "--level", "module", "--parameters", str(params_file)])
        assert result.exit_code == 1
        assert "--module is required" in result.stdout

    def test_profiling_module_missing_dataset_flag(self, tmp_path):
        params_file = tmp_path / "params.yaml"
        params_file.write_text("")
        result = runner.invoke(
            app,
            ["profiling", "--level", "module", "--parameters", str(params_file), "--module", "DayAheadOrders"],
        )
        assert result.exit_code == 1
        assert "--dataset is required" in result.stdout

    def test_profiling_module_nonexistent_dataset(self, tmp_path):
        params_file = tmp_path / "params.yaml"
        params_file.write_text("")
        result = runner.invoke(
            app,
            [
                "profiling",
                "--level",
                "module",
                "--parameters",
                str(params_file),
                "--module",
                "DayAheadOrders",
                "--dataset",
                str(tmp_path / "nonexistent"),
            ],
        )
        assert result.exit_code == 1
        assert "Dataset directory not found" in result.stdout

    def test_profiling_module_invalid_module_name(self, tmp_path):
        params_file = tmp_path / "params.yaml"
        params_file.write_text("")
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        result = runner.invoke(
            app,
            [
                "profiling",
                "--level",
                "module",
                "--parameters",
                str(params_file),
                "--module",
                "NotAModule",
                "--dataset",
                str(dataset_dir),
            ],
        )
        assert result.exit_code == 1

    # --- Success paths ---

    @patch("atlas.app.run_workflow")
    def test_profiling_workflow_calls_run(self, mock_run, tmp_path):
        params_file = tmp_path / "params.yaml"
        params_file.write_text("")
        result = runner.invoke(app, ["profiling", "--level", "workflow", "--parameters", str(params_file)])
        assert result.exit_code == 0
        mock_run.assert_called_once_with(params_file, None)

    @patch("atlas.app.run_workflow")
    def test_profiling_workflow_passes_output(self, mock_run, tmp_path):
        params_file = tmp_path / "params.yaml"
        params_file.write_text("")
        output_path = tmp_path / "my_results"
        result = runner.invoke(
            app,
            ["profiling", "--level", "workflow", "--parameters", str(params_file), "--output", str(output_path)],
        )
        assert result.exit_code == 0
        mock_run.assert_called_once_with(params_file, output_path)

    @patch("atlas.app.run_module")
    @patch("atlas.app.ModuleRegistry")
    def test_profiling_module_calls_run(self, mock_registry, mock_run, tmp_path):
        params_file = tmp_path / "params.yaml"
        params_file.write_text("")
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        result = runner.invoke(
            app,
            [
                "profiling",
                "--level",
                "module",
                "--parameters",
                str(params_file),
                "--module",
                "DayAheadOrders",
                "--dataset",
                str(dataset_dir),
            ],
        )
        assert result.exit_code == 0
        mock_run.assert_called_once_with(params_file, "DayAheadOrders", dataset_dir, None)

    @patch("atlas.app.run_module")
    @patch("atlas.app.ModuleRegistry")
    def test_profiling_module_passes_output(self, mock_registry, mock_run, tmp_path):
        params_file = tmp_path / "params.yaml"
        params_file.write_text("")
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        output_path = tmp_path / "my_results"
        result = runner.invoke(
            app,
            [
                "profiling",
                "--level",
                "module",
                "--parameters",
                str(params_file),
                "--module",
                "DayAheadOrders",
                "--dataset",
                str(dataset_dir),
                "--output",
                str(output_path),
            ],
        )
        assert result.exit_code == 0
        mock_run.assert_called_once_with(params_file, "DayAheadOrders", dataset_dir, output_path)


class TestAntaresToAtlasRunCommand:
    """Tests for the 'atlas antares-to-atlas run' command."""

    def test_run_missing_parameters_file(self, tmp_path):
        """Test that command fails when parameters file doesn't exist."""
        study_dir = tmp_path / "study"
        study_dir.mkdir()
        nonexistent_params = tmp_path / "nonexistent.yaml"
        output_dir = tmp_path / "output"

        result = runner.invoke(
            app,
            ["antares-to-atlas", "run", str(study_dir), "-p", str(nonexistent_params), "-o", str(output_dir)],
        )
        assert result.exit_code == 1
        assert "Parameters file not found" in result.stdout

    def test_run_missing_study_directory(self, tmp_path):
        """Test that command fails when study directory doesn't exist."""
        nonexistent_study = tmp_path / "nonexistent_study"
        params_file = tmp_path / "params.yaml"
        params_file.write_text("")
        output_dir = tmp_path / "output"

        result = runner.invoke(
            app,
            ["antares-to-atlas", "run", str(nonexistent_study), "-p", str(params_file), "-o", str(output_dir)],
        )
        assert result.exit_code == 1
        assert "Study directory not found" in result.stdout

    @patch("atlas.app.AntaresToAtlas")
    def test_run_with_valid_inputs(self, mock_antares, tmp_path):
        """Test that command succeeds with valid inputs (mocked execution)."""
        study_dir = tmp_path / "study"
        study_dir.mkdir()
        params_file = tmp_path / "params.yaml"
        params_file.write_text("")
        output_dir = tmp_path / "output"

        mock_converter = MagicMock()
        mock_dataset = MagicMock()
        mock_antares.from_file.return_value = mock_converter
        mock_converter.convert.return_value = mock_dataset

        result = runner.invoke(
            app,
            ["antares-to-atlas", "run", str(study_dir), "-p", str(params_file), "-o", str(output_dir)],
        )

        assert result.exit_code == 0
        mock_antares.from_file.assert_called_once()
        mock_converter.convert.assert_called_once_with(study_dir)
        mock_dataset.to_directory.assert_called_once()

    @patch("atlas.app.AntaresToAtlas")
    def test_run_conversion_failure(self, mock_antares, tmp_path):
        """Test that command fails gracefully when conversion raises an exception."""
        study_dir = tmp_path / "study"
        study_dir.mkdir()
        params_file = tmp_path / "params.yaml"
        params_file.write_text("")
        output_dir = tmp_path / "output"

        mock_converter = MagicMock()
        mock_antares.from_file.return_value = mock_converter
        mock_converter.convert.side_effect = Exception("Conversion error")

        result = runner.invoke(
            app,
            ["antares-to-atlas", "run", str(study_dir), "-p", str(params_file), "-o", str(output_dir)],
        )

        assert result.exit_code == 1

    @patch("atlas.app.AntaresToAtlas")
    def test_run_load_failure(self, mock_antares, tmp_path):
        """Test that command fails gracefully when loading parameters raises an exception."""
        study_dir = tmp_path / "study"
        study_dir.mkdir()
        params_file = tmp_path / "params.yaml"
        params_file.write_text("")
        output_dir = tmp_path / "output"

        mock_antares.from_file.side_effect = Exception("Bad YAML")

        result = runner.invoke(
            app,
            ["antares-to-atlas", "run", str(study_dir), "-p", str(params_file), "-o", str(output_dir)],
        )

        assert result.exit_code == 1
        assert "Failed to load parameters" in result.stdout


class TestAntaresToAtlasValidateCommand:
    """Tests for the 'atlas antares-to-atlas validate' command."""

    def test_validate_missing_parameters_file(self, tmp_path):
        """Test that command fails when parameters file doesn't exist."""
        nonexistent_params = tmp_path / "nonexistent.yaml"

        result = runner.invoke(app, ["antares-to-atlas", "validate", "-p", str(nonexistent_params)])
        assert result.exit_code == 1
        assert "Parameters file not found" in result.stdout

    @patch("atlas.app.AntaresToAtlas")
    def test_validate_with_valid_inputs(self, mock_antares, tmp_path):
        """Test that validate succeeds and prints parameters summary."""
        params_file = tmp_path / "params.yaml"
        params_file.write_text("")

        mock_converter = MagicMock()
        mock_antares.from_file.return_value = mock_converter
        mock_p = mock_converter.parameters
        mock_p.hypothesis = None
        mock_p.market_areas = ["FR", "DE"]
        mock_p.hydro.initialization_curve = None
        mock_p.hydro.path_inflows = None
        mock_p.baseline_displacement_energy = None
        mock_p.disp_energy_node_parameters = None
        mock_converter.list_converter_details.return_value = [("ConverterA", "desc A")]

        result = runner.invoke(app, ["antares-to-atlas", "validate", "-p", str(params_file)])

        assert result.exit_code == 0
        mock_antares.from_file.assert_called_once()
        mock_converter.list_converter_details.assert_called_once()


class TestAntaresToAtlasConvertersCommand:
    """Tests for the 'atlas antares-to-atlas converters' command."""

    def test_converters_missing_parameters_file(self, tmp_path):
        """Test that command fails when parameters file doesn't exist."""
        nonexistent_params = tmp_path / "nonexistent.yaml"

        result = runner.invoke(app, ["antares-to-atlas", "converters", "-p", str(nonexistent_params)])
        assert result.exit_code == 1
        assert "Parameters file not found" in result.stdout

    @patch("atlas.app.AntaresToAtlas")
    def test_converters_with_valid_inputs(self, mock_antares, tmp_path):
        """Test that converters command lists converters from the parameters file."""
        params_file = tmp_path / "params.yaml"
        params_file.write_text("")

        mock_converter = MagicMock()
        mock_antares.from_file.return_value = mock_converter
        mock_converter.list_converter_details.return_value = [
            ("ConverterA", "desc A"),
            ("ConverterB", "desc B"),
        ]

        result = runner.invoke(app, ["antares-to-atlas", "converters", "-p", str(params_file)])

        assert result.exit_code == 0
        mock_antares.from_file.assert_called_once()
        mock_converter.list_converter_details.assert_called_once()


class TestCLIHelp:
    """Tests for CLI help and documentation."""

    def test_main_help_succeeds(self):
        """Test that main help command works."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "run" in result.stdout
        assert "version" in result.stdout

    def test_run_command_help(self):
        """Test that run command help works."""
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "module" in result.stdout
        assert "workflow" in result.stdout

    def test_prometheus_to_atlas_command_help(self):
        """Test that prometheus-to-atlas run subcommand help works."""
        result = runner.invoke(app, ["prometheus-to-atlas", "run", "--help"])
        assert result.exit_code == 0
        assert "timeseries" in result.stdout.lower()
        assert "hdf5" in result.stdout.lower()

    def test_prometheus_to_atlas_recursive_command_help(self):
        """Test that prometheus-to-atlas batch subcommand help works."""
        result = runner.invoke(app, ["prometheus-to-atlas", "batch", "--help"])
        assert result.exit_code == 0
        assert "root" in result.stdout.lower()
