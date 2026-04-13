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

    @patch("atlas.app.CurrentInputState")
    @patch("atlas.app.ModuleRegistry")
    def test_run_module_with_valid_inputs(self, mock_registry, mock_dataset, tmp_path):
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

        # Setup mock run
        mock_output_dataset = MagicMock()
        mock_output_dataset.change_sets = []
        mock_module_instance.run.return_value = mock_output_dataset

        # Setup mock dataset
        mock_dataset.from_directory.return_value = MagicMock()

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
        mock_module_instance.run.assert_called_once()


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
            output_dataset_path: ./output
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
            ["prometheus-to-atlas", str(nonexistent_ts), str(hdf5_file), str(output_dir)],
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
            ["prometheus-to-atlas", str(ts_folder), str(nonexistent_hdf5), str(output_dir)],
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
            ["prometheus-to-atlas", str(ts_folder), str(hdf5_file), str(output_dir)],
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
                str(ts_folder),
                str(hdf5_file),
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
            ["prometheus-to-atlas-recursive", str(nonexistent_root), str(output_root)],
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
            ["prometheus-to-atlas-recursive", str(file_path), str(output_root)],
        )
        assert result.exit_code == 1
        assert "Path is not a directory" in result.stdout

    def test_recursive_no_valid_module_directories(self, tmp_path):
        """Test that command fails when no valid module directories are found."""
        root_dir = tmp_path / "root"
        root_dir.mkdir()
        # Create a directory without 'ts' folder
        (root_dir / "invalid_module").mkdir()
        output_root = tmp_path / "output"

        result = runner.invoke(
            app,
            ["prometheus-to-atlas-recursive", str(root_dir), str(output_root)],
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
            ["prometheus-to-atlas-recursive", str(root_dir), str(output_root), "--no-use-mp"],
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
            ["prometheus-to-atlas-recursive", str(root_dir), str(output_root), "--no-use-mp"],
        )

        # Should exit with error code since no modules were processed
        assert result.exit_code == 1


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
        """Test that prometheus-to-atlas command help works."""
        result = runner.invoke(app, ["prometheus-to-atlas", "--help"])
        assert result.exit_code == 0
        assert "timeseries" in result.stdout.lower()
        assert "hdf5" in result.stdout.lower()

    def test_prometheus_to_atlas_recursive_command_help(self):
        """Test that prometheus-to-atlas-recursive command help works."""
        result = runner.invoke(app, ["prometheus-to-atlas-recursive", "--help"])
        assert result.exit_code == 0
        assert "root" in result.stdout.lower()
