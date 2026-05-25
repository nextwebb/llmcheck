from __future__ import annotations

import base64
import csv
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
PROJECT = "llmcheck"
VERSION = "0.3.0"


def _dist_info_dir() -> str:
    return f"{PROJECT}-{VERSION}.dist-info"


def _wheel_name() -> str:
    return f"{PROJECT}-{VERSION}-py3-none-any.whl"


def _metadata_text() -> str:
    return (
        "Metadata-Version: 2.1\n"
        f"Name: {PROJECT}\n"
        f"Version: {VERSION}\n"
        "Summary: Turn bad LLM/RAG runs into local regression checks for CI\n"
        "Requires-Python: >=3.10\n"
        "Requires-Dist: PyYAML>=6.0\n"
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


def build_wheel(wheel_directory: str, config_settings=None, metadata_directory=None) -> str:
    return _write_wheel(wheel_directory, _editable_wheel_contents())


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
    return dist_info.name


def get_requires_for_build_sdist(config_settings=None) -> list[str]:
    return []


def build_sdist(sdist_directory: str, config_settings=None) -> str:
    raise NotImplementedError("sdist build is not implemented for this local backend")
