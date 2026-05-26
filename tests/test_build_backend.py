from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_build_backend():
    path = Path(__file__).resolve().parents[1] / "build_backend.py"
    spec = importlib.util.spec_from_file_location("llmcheck_build_backend", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_metadata_exposes_test_extra() -> None:
    build_backend = _load_build_backend()
    metadata = build_backend._metadata_text()
    assert "Provides-Extra: test" in metadata
    assert 'Requires-Dist: pytest>=8.0; extra == "test"' in metadata
