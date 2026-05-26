from __future__ import annotations

import importlib
import pkgutil

import llmcheck


def test_all_packaged_llmcheck_modules_import() -> None:
    failures: list[str] = []
    for module in pkgutil.walk_packages(llmcheck.__path__, prefix="llmcheck."):
        try:
            importlib.import_module(module.name)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{module.name}: {type(exc).__name__}: {exc}")

    assert failures == []
