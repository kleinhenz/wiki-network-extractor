# Repository Guidelines

## Project Structure & Module Organization

This is a small Python package for extracting link graphs from Wikimedia XML dumps.

- `src/wiki_network_extractor/__init__.py` contains the core parsing, normalization, graph construction, and HDF5 writing logic.
- `src/wiki_network_extractor/__main__.py` defines the `wikinet` CLI entry point.
- `tests/test_core.py` contains unit tests for redirects, namespace filtering, XML parsing, and CSR output.
- `README.md` documents installation, usage, and implementation notes.
- `data/` is for local dump/output files and should not be treated as source code.

## Build, Test, and Development Commands

- `uv sync --group dev` installs the package and development dependencies from `pyproject.toml`/`uv.lock`.
- `uv run python -m pytest` runs the test suite. Prefer module form because stale virtualenv script shims may point at old paths.
- `uv run ruff check .` runs lint checks.
- `uv run ty check` runs static type checks.
- `uv run wikinet xml2json input.xml.bz2 output.json` converts a compressed Wikimedia XML dump to NDJSON.
- `uv run wikinet json2hdf input.json output.h5` converts NDJSON to the HDF5 graph format.

## Coding Style & Naming Conventions

Use Python 3.12+ and standard 4-space indentation. Keep functions small and named with `snake_case`; constants use `UPPER_SNAKE_CASE` when appropriate. Existing public functions such as `xml2json`, `json2graph`, and `json2hdf` are intentionally concise API names, so preserve them unless changing the public interface deliberately.

Prefer clear standard-library and NumPy/HDF5 APIs over ad hoc parsing where possible. Run `ruff` before submitting changes and remove unused imports or dead code.

## Testing Guidelines

Tests use `pytest` with `unittest.TestCase` style assertions. Add tests in `tests/test_core.py` or split into `tests/test_*.py` files as coverage grows. Name tests by behavior, for example `test_redirect_cycles_are_ignored`.

For parser or graph changes, include small synthetic XML/NDJSON fixtures in the test body and assert exact titles, adjacency lists, or CSR arrays. Cover edge cases such as redirects, namespaces, duplicate links, and title normalization.

## Commit & Pull Request Guidelines

Recent commits use short, imperative, lowercase subjects, for example `improve parsing` and `update packaging`. Keep commit messages focused on one logical change.

Pull requests should include a brief description, the commands run for verification, and notes about any data-format or CLI behavior changes. Link related issues when available. Screenshots are not relevant unless documentation rendering changes.

## Agent-Specific Instructions

Do not commit generated dump outputs or large local HDF5/XML artifacts from `data/`. When changing output schemas, update both tests and README storage-format documentation in the same change.
