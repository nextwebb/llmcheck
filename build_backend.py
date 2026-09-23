from __future__ import annotations

import base64
import csv
import hashlib
import re
import tarfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
PROJECT = "llmcheck"
VERSION = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.MULTILINE).group(1)


def _dist_info_dir() -> str:
    return f"{PROJECT}-{VERSION}.dist-info"


def _wheel_name() -> str:
    return f"{PROJECT}-{VERSION}-py3-none-any.whl"


def _metadata_text() -> str:
    return (
        "Metadata-Version: 2.4\n"
        "License-Expression: Apache-2.0\n"
        "License-File: LICENSE\n"
        "License-File: NOTICE\n"
        f"Name: {PROJECT}\n"
        f"Version: {VERSION}\n"
        "Summary: Turn bad LLM/RAG runs into local regression checks for CI\n"
        "Requires-Python: >=3.10\n"
        "Requires-Dist: PyYAML>=6.0\n"
        "Provides-Extra: test\n"
        'Requires-Dist: pytest>=8.0; extra == "test"\n'
        "Description-Content-Type: text/markdown\n"
        "Project-URL: Source, https://github.com/nextwebb/llmcheck\n"
        "\n"
        + (ROOT / "README.md").read_text(encoding="utf-8")
    )


def _wheel_text() -> str:
    return (
        "Wheel-Version: 1.0\n"
        "Generator: llmcheck-local-backend\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    )


def _entry_points_text() -> str:
    return "[console_scripts]\nllmcheck = llmcheck.cli:main\n"


def _record_line(path: str, data: bytes) -> tuple[str, str, str]:
    digest = hashlib.sha256(data).digest()
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return path, f"sha256={encoded}", str(len(data))


def _editable_wheel_contents() -> list[tuple[str, bytes]]:
    dist_info = _dist_info_dir()
    package_stub = (
        "from pathlib import Path\n"
        f"_SRC_PACKAGE = Path({str((SRC / PROJECT).resolve())!r})\n"
        f"__file__ = str(_SRC_PACKAGE / '__init__.py')\n"
        "__path__ = [str(_SRC_PACKAGE)]\n"
        "with open(__file__, 'rb') as _fh:\n"
        "    exec(compile(_fh.read(), __file__, 'exec'))\n"
    ).encode("utf-8")
    files = [
        (f"{PROJECT}/__init__.py", package_stub),
        (f"{dist_info}/METADATA", _metadata_text().encode("utf-8")),
        (f"{dist_info}/WHEEL", _wheel_text().encode("utf-8")),
        (f"{dist_info}/entry_points.txt", _entry_points_text().encode("utf-8")),
        (f"{dist_info}/top_level.txt", f"{PROJECT}\n".encode("utf-8")),
    ]
    files.extend((f"{dist_info}/licenses/{name}", (ROOT / name).read_bytes()) for name in ("LICENSE", "NOTICE"))
    return files


def _write_wheel(wheel_directory: str, files: list[tuple[str, bytes]]) -> str:
    wheel_directory_path = Path(wheel_directory)
    wheel_directory_path.mkdir(parents=True, exist_ok=True)
    wheel_path = wheel_directory_path / _wheel_name()

    records = [_record_line(path, data) for path, data in files]
    record_path = f"{_dist_info_dir()}/RECORD"

    with ZipFile(wheel_path, "w", compression=ZIP_DEFLATED) as zf:
        for path, data in files:
            zf.writestr(path, data)

        rows: list[tuple[str, str, str]] = list(records)
        rows.append((record_path, "", ""))
        record_bytes = _csv_bytes(rows)
        zf.writestr(record_path, record_bytes)

    return wheel_path.name


def _csv_bytes(rows: list[tuple[str, str, str]]) -> bytes:
    from io import StringIO

    buf = StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


DEMO_ASSETS = {"companion.zip", "cases.json", "live-evaluation.json"}
SDIST_DOCS = {
    "docs/reference.md", "docs/release-validation.md", "docs/agentic-poc-testing.md",
    "docs/assets/llmcheck-demo.gif",
}


def _archive_name(path, base) -> str:
    # ZIP and tar member names always use '/', including on Windows.
    return path.relative_to(base).as_posix()


def _safe_file(path: Path, base: Path) -> bool:
    relative = path.relative_to(base)
    return (
        path.is_file()
        and not any(part.startswith(".") or part == "__pycache__" for part in relative.parts)
        and not any(parent.is_symlink() for parent in (path, *path.parents) if parent != base and base in parent.parents)
    )


def _package_files():
    package = SRC / PROJECT
    for path in sorted(package.rglob("*")):
        if not _safe_file(path, SRC):
            continue
        relative = path.relative_to(package)
        if path.suffix == ".py" or (relative.parent.as_posix() == "demo_assets" and relative.name in DEMO_ASSETS):
            yield path


def build_wheel(wheel_directory: str, config_settings=None, metadata_directory=None) -> str:
    files = [(_archive_name(path, SRC), path.read_bytes()) for path in _package_files()]
    files.extend((name, data) for name, data in _editable_wheel_contents() if name.startswith(_dist_info_dir() + "/"))
    return _write_wheel(wheel_directory, files)


def build_editable(wheel_directory: str, config_settings=None, metadata_directory=None) -> str:
    return _write_wheel(wheel_directory, _editable_wheel_contents())


def get_requires_for_build_wheel(config_settings=None) -> list[str]:
    return []


def get_requires_for_build_editable(config_settings=None) -> list[str]:
    return []


def prepare_metadata_for_build_wheel(metadata_directory: str, config_settings=None) -> str:
    return _prepare_metadata(metadata_directory)


def prepare_metadata_for_build_editable(metadata_directory: str, config_settings=None) -> str:
    return _prepare_metadata(metadata_directory)


def _prepare_metadata(metadata_directory: str) -> str:
    dist_info = Path(metadata_directory) / _dist_info_dir()
    dist_info.mkdir(parents=True, exist_ok=True)
    (dist_info / "METADATA").write_text(_metadata_text(), encoding="utf-8")
    (dist_info / "WHEEL").write_text(_wheel_text(), encoding="utf-8")
    (dist_info / "entry_points.txt").write_text(_entry_points_text(), encoding="utf-8")
    (dist_info / "top_level.txt").write_text(f"{PROJECT}\n", encoding="utf-8")
    licenses = dist_info / "licenses"
    licenses.mkdir(exist_ok=True)
    for name in ("LICENSE", "NOTICE"):
        (licenses / name).write_bytes((ROOT / name).read_bytes())
    return dist_info.name


def get_requires_for_build_sdist(config_settings=None) -> list[str]:
    return []


def build_sdist(sdist_directory: str, config_settings=None) -> str:
    destination = Path(sdist_directory)
    destination.mkdir(parents=True, exist_ok=True)
    prefix = f"{PROJECT}-{VERSION}"
    target = destination / f"{prefix}.tar.gz"
    root_names = {"pyproject.toml", "build_backend.py", "README.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md", "LICENSE", "NOTICE", "LICENSE.md", "LICENSE.txt"}
    with tarfile.open(target, "w:gz") as archive:
        candidates = set(_package_files())
        candidates.update(ROOT / name for name in root_names)
        candidates.update(ROOT / name for name in SDIST_DOCS)
        candidates.update((ROOT / "tests").glob("test_*.py"))
        candidates.add(ROOT / "tests" / "conftest.py")
        for path in sorted(candidates):
            if not _safe_file(path, ROOT):
                continue
            archive.add(path, arcname=f"{prefix}/{_archive_name(path, ROOT)}", recursive=False)
        import io
        metadata = _metadata_text().encode("utf-8")
        info = tarfile.TarInfo(f"{prefix}/PKG-INFO")
        info.size = len(metadata)
        archive.addfile(info, io.BytesIO(metadata))
    return target.name
