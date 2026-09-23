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


def test_regular_wheel_contains_portable_package_and_valid_records(tmp_path) -> None:
    import base64
    import csv
    import hashlib
    import io
    import subprocess
    import sys
    from zipfile import ZipFile

    backend = _load_build_backend()
    wheel = tmp_path / backend.build_wheel(str(tmp_path))
    installed = tmp_path / "installed"
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "llmcheck/cli.py" in names
        assert "llmcheck/sdk/openai.py" in names
        assert "_SRC_PACKAGE" not in archive.read("llmcheck/__init__.py").decode()
        assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)
        record = next(name for name in names if name.endswith("/RECORD"))
        for name, digest, size in csv.reader(io.StringIO(archive.read(record).decode())):
            if name == record:
                continue
            data = archive.read(name)
            expected = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
            assert digest == "sha256=" + expected
            assert int(size) == len(data)
        archive.extractall(installed)
    code = (
        "import sys; sys.path.insert(0, " + repr(str(installed)) + "); "
        "import llmcheck; from llmcheck.cli import main; "
        "assert llmcheck.__file__.startswith(" + repr(str(installed)) + "); "
        "sys.argv=['llmcheck', '--help']; main()"
    )
    result = subprocess.run([sys.executable, "-I", "-c", code], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "run-suite" in result.stdout


def test_sdist_rebuilds_away_from_checkout_and_excludes_workspace_data(tmp_path) -> None:
    import subprocess
    import sys
    import tarfile
    from zipfile import ZipFile

    backend = _load_build_backend()
    sdist = tmp_path / backend.build_sdist(str(tmp_path))
    extracted = tmp_path / "unpacked"
    extracted.mkdir()
    with tarfile.open(sdist) as archive:
        names = archive.getnames()
        assert any(name.endswith("/pyproject.toml") for name in names)
        assert any(name.endswith("/PKG-INFO") for name in names)
        assert not any(part in {".env", ".llmcheck", ".git", ".venv", "__pycache__"} for name in names for part in Path(name).parts)
        assert not any(name.endswith((".db", ".sqlite", ".sqlite3", ".pyc")) for name in names)
        for member in archive.getmembers():
            assert not member.name.startswith("/") and ".." not in Path(member.name).parts
        archive.extractall(extracted)
    source = next(extracted.iterdir())
    target = tmp_path / "rebuilt"
    result = subprocess.run([sys.executable, "-c", "import build_backend; print(build_backend.build_wheel(" + repr(str(target)) + "))"], cwd=source, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    with ZipFile(next(target.glob("*.whl"))) as archive:
        assert "llmcheck/cli.py" in archive.namelist()
        metadata = archive.read(next(name for name in archive.namelist() if name.endswith("/METADATA"))).decode()
        assert "Description-Content-Type: text/markdown" in metadata


def test_package_data_is_included_and_symlinks_are_excluded(tmp_path, monkeypatch) -> None:
    from zipfile import ZipFile
    backend = _load_build_backend()
    source = tmp_path / "src"
    package = source / "llmcheck"
    assets = package / "demo_assets"
    assets.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (assets / "companion.zip").write_bytes(b"synthetic-fixture")
    secret = tmp_path / "secret.txt"
    secret.write_text("do not package")
    (assets / "outside.txt").symlink_to(secret)
    monkeypatch.setattr(backend, "SRC", source)
    wheel = backend.build_wheel(str(tmp_path))
    with ZipFile(tmp_path / wheel) as archive:
        assert archive.read("llmcheck/demo_assets/companion.zip") == b"synthetic-fixture"
        assert "llmcheck/demo_assets/outside.txt" not in archive.namelist()
