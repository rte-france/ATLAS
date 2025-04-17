# Contributing 

Thanks for taking the time to contribute!  
We welcome bug reports, feature suggestions, and pull requests.

## 🛠️ Project Setup

This project uses [`uv`](https://github.com/astral-sh/uv/#installation) for dependency management and Python environment isolation.

### 1. Clone the Repository

```bash
git clone https://github.com/rte-france/ATLAS.git
```

### Set up the Environment

```bash
uv sync --all-groups
```
If you're contributing new dependencies, install them with:

```bash
uv add package-name
```

## 🧪 Running Tests

We use pytest for testing. To run the tests:

```bash
uv run pytest .
```

> Make sure all tests pass before submitting a PR.

## 🧹 Code Style

We use `ruff` to format and lint the code:

```bash
uv run ruff format atlas
uv run ruff check atlas
```

We also use `mypy` for typing analysis :

```bash
uv run mypy atlas
```

## 🧩 Making a Pull Request


Before contributing code, make sure you've:

- Synced with the latest version of the `develop` branch.
- Created a **descriptive branch name** using one of the following conventions:

### 🔖 Branch Naming Conventions

- `feat/your-feature-name` or `feature/your-feature-name` – for new features  

- `fix/your-fix-description` – for bug fixes  

- `chore/your-task` – for non-functional tasks like config or dependency updates  

- `docs/your-doc-change` – for documentation-only changes  

- `test/your-test-task` – for adding or improving tests  
