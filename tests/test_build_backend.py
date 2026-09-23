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
    collected = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=source, capture_output=True, text=True)
    assert collected.returncode == 0, collected.stdout + collected.stderr
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


def test_apache_license_metadata_and_files_survive_all_build_paths(tmp_path) -> None:
    import tarfile
    from email.parser import Parser
    from zipfile import ZipFile

    backend = _load_build_backend()
    metadata = Parser().parsestr(backend._metadata_text())
    assert metadata["Metadata-Version"] == "2.4"
    assert metadata["License-Expression"] == "Apache-2.0"
    assert metadata.get_all("License-File") == ["LICENSE", "NOTICE"]
    assert metadata["License"] is None
    expected = {name: (backend.ROOT / name).read_bytes() for name in ("LICENSE", "NOTICE")}
    assert b"Apache License" in expected["LICENSE"]
    assert b"Copyright 2026 Peterson Oaikhenah" in expected["NOTICE"]
    for method in (backend.build_wheel, backend.build_editable):
        with ZipFile(tmp_path / method(str(tmp_path))) as archive:
            for name, content in expected.items():
                assert archive.read(f"{backend._dist_info_dir()}/licenses/{name}") == content
    metadata_dir = tmp_path / "metadata"
    info = backend.prepare_metadata_for_build_wheel(str(metadata_dir))
    for name, content in expected.items():
        assert (metadata_dir / info / "licenses" / name).read_bytes() == content
    with tarfile.open(tmp_path / backend.build_sdist(str(tmp_path))) as archive:
        prefix = f"{backend.PROJECT}-{backend.VERSION}"
        for name, content in expected.items():
            assert archive.extractfile(f"{prefix}/{name}").read() == content
        pkg = Parser().parsestr(archive.extractfile(f"{prefix}/PKG-INFO").read().decode())
        assert pkg["License-Expression"] == "Apache-2.0"
        assert pkg.get_all("License-File") == ["LICENSE", "NOTICE"]


def test_distribution_boundaries_exclude_hidden_files_and_private_dumps(tmp_path, monkeypatch) -> None:
    import shutil
    import tarfile
    from zipfile import ZipFile

    backend = _load_build_backend()
    root = tmp_path / "project"
    package = root / "src" / "llmcheck"
    package.mkdir(parents=True)
    for name in ("README.md", "LICENSE", "NOTICE", "pyproject.toml", "build_backend.py"):
        shutil.copyfile(backend.ROOT / name, root / name)
    (package / "__init__.py").write_text("")
    included = ["demo_assets/cases.json", "demo_assets/live-evaluation.json", "demo_assets/companion.zip"]
    excluded = [".env", "debug.json", "customer-dump.txt", "capture.db", "untracked.zip", ".private/settings.py", "demo_assets/.env", "demo_assets/private-dump.json"]
    for name in included + excluded:
        path = package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic-test-data")
    (root / "docs").mkdir()
    (root / "docs" / "private-dump.json").write_text("do not package")
    monkeypatch.setattr(backend, "ROOT", root)
    monkeypatch.setattr(backend, "SRC", root / "src")
    with ZipFile(tmp_path / backend.build_wheel(str(tmp_path))) as archive:
        names = set(archive.namelist())
        assert all("llmcheck/" + name in names for name in included)
        assert all("llmcheck/" + name not in names for name in excluded)
        assert all("\\" not in name for name in names)
    with tarfile.open(tmp_path / backend.build_sdist(str(tmp_path))) as archive:
        names = set(archive.getnames())
        prefix = f"{backend.PROJECT}-{backend.VERSION}/src/llmcheck/"
        assert all(prefix + name in names for name in included)
        assert all(prefix + name not in names for name in excluded)
        assert not any(name.endswith("docs/private-dump.json") for name in names)
        assert all("\\" not in name for name in names)


def test_archive_paths_are_posix_even_when_source_paths_are_windows() -> None:
    from pathlib import PureWindowsPath
    backend = _load_build_backend()
    base = PureWindowsPath(r"C:\checkout\src")
    path = base / "llmcheck" / "demo_assets" / "cases.json"
    assert backend._archive_name(path, base) == "llmcheck/demo_assets/cases.json"
