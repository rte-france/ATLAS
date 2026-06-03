# Installation

## Basic Installation

This project is under development. There is no public release yet.

### Prerequisites

- Python 3.13 or higher
- [uv](https://docs.astral.sh/uv/#installation) package manager (recommended)

### Install from Source

Clone the repository and set up your environment:

```bash
git clone https://github.com/rte-france/ATLAS.git && cd ATLAS
uv sync --all-groups
```

### Future Installation (Planned)

Once released, Atlas will be available via pip:

```bash
pip install atlas-rte

# or using uv
uv add atlas-rte
```

## Solvers

Atlas uses OR-Tools as the default optimization modeler, you can use any compatible solver. We provide special support for the commercial Xpress solver.

### Default solvers (included in the basis OR-Tools environment)

OR-Tools is installed automatically with Atlas and works out of the box. No additional configuration needed.
Several solvers are natively included in OR-Tools (SCIP, CP-SAT, etc.).
In the Atlas context, the majority of optimization problems are Mixed-Integer Linear Problems. We recommand SCIP for its ability to deal with this type of problems.

### Xpress (Optional)

For improved performance, you can install the Xpress commercial solver. The OR-Tools version used in Atlas is compatible with Xpress, meaning that there is no additional task for the user except specifying "XPRESS" as their solver in module parameters.

#### Windows Installation

1. Download the installer from [Artelys](https://www.artelys.com/fr/espace-client/telecharger-xpress/) (account required)
2. Run the installer
3. Move your license file `xpauth.xpr` to `xpressmp/bin/`

#### Linux Installation

For detailed information, see the [FICO Xpress documentation](https://www.fico.com/fico-xpress-optimization/docs/dms2021-02/installguide/dhtml/chapinst1_sec_secunix.html).

1. Download the installer from [Artelys](https://www.artelys.com/fr/espace-client/telecharger-xpress/) (account required)
2. Move the archive to `/opt/xpressmp`
3. Extract and enter the directory: `cd <archive_uncompressed>`
4. Run the installer with **static licensing**:

```bash
sudo chmod +x install.sh
sudo ./install.sh
```

5. Copy your license file `xpauth.xpr` to `/opt/xpressmp/`
6. Add environment variables to `~/.bashrc` or `~/.zshrc`:

```bash
export XPRESS_DIR="/opt/xpressmp"  # Add /y if installer created a subfolder
export XPAUTH_PATH="/opt/xpressmp/xpauth.xpr"
```

7. Verify the installation:

```python
from atlas import OptimisationModel

model = OptimisationModel('xpress')
```

## Next Steps

Once installed, proceed to:

- [Quick Start Tutorial](quickstart.md) - Get up and running in 5 minutes
- [Your First Simulation](first-simulation.md) - Complete walkthrough with sample data
- [Module Pattern](../modules/module-pattern.md) - Understand Atlas architecture
