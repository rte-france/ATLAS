# Atlas

## Python Installation

This project has been tested on Python version 3.10.
Clone the project:
```bash
git clone https://github.com/rte-france/ATLAS.git
```

### Create virtual environment and library dependency

1. Install [uv](https://docs.astral.sh/uv/#installation):

for windows, using powershell:
```bash
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
for mac/linux:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
Restart your shell after uv installation. You should be able to get the uv version with ```uv --version```
2. Install python 3.10
```bash
uv python install 3.10
```
3. Create virtual environment, and activate it as described in your terminal:
```bash
uv venv
```
