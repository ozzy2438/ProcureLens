#!/usr/bin/env python3
"""Make the bundled local MLflow registry portable and free of workstation paths."""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path
from types import CodeType, FunctionType

import cloudpickle

ABSOLUTE_SOURCE = re.compile(rb"/(?:Users|home)/[^/]+/[^\x00\n\r]+?ProcureLens/")


def _portable_filename(filename: str) -> str:
    if "site-packages/mlflow/" in filename:
        return "mlflow/" + filename.split("site-packages/mlflow/", 1)[1]
    if "/src/procurelens/" in filename:
        return "src/procurelens/" + filename.split("/src/procurelens/", 1)[1]
    return filename


def _portable_code(code: CodeType) -> CodeType:
    constants = tuple(
        _portable_code(value) if isinstance(value, CodeType) else value
        for value in code.co_consts
    )
    return code.replace(
        co_filename=_portable_filename(code.co_filename),
        co_consts=constants,
    )


def _sanitize_class(class_object: type[object], seen: set[int]) -> None:
    if id(class_object) in seen:
        return
    seen.add(id(class_object))
    for value in vars(class_object).values():
        if isinstance(value, FunctionType):
            _sanitize_function(value, seen)
        elif isinstance(value, (staticmethod, classmethod)):
            _sanitize_function(value.__func__, seen)


def _sanitize_function(function: FunctionType, seen: set[int]) -> None:
    if id(function) in seen:
        return
    seen.add(id(function))
    function.__code__ = _portable_code(function.__code__)
    global_file = function.__globals__.get("__file__")
    if isinstance(global_file, str):
        function.__globals__["__file__"] = _portable_filename(global_file)
    for value in function.__globals__.values():
        if isinstance(value, type) and value.__module__ in {
            "__main__",
            "procurelens.models.train_fit_scorer",
        }:
            _sanitize_class(value, seen)
    wrapped = getattr(function, "__wrapped__", None)
    if isinstance(wrapped, FunctionType):
        _sanitize_function(wrapped, seen)


def sanitize_pyfunc_pickle(path: Path) -> None:
    with path.open("rb") as handle:
        model = cloudpickle.load(handle)

    _sanitize_class(type(model), set())

    with path.open("wb") as handle:
        cloudpickle.dump(model, handle)

    if ABSOLUTE_SOURCE.search(path.read_bytes()):
        raise RuntimeError(f"absolute source path remains in {path}")


def sanitize_mlmodel(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("artifact_path: /") and "/mlruns/artifacts/" in line:
            suffix = line.split("/mlruns/artifacts/", 1)[1]
            lines[index] = f"artifact_path: mlflow-artifacts:/{suffix}"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def sanitize_database(database: Path, repository_root: Path) -> None:
    artifact_prefix = str((repository_root / "mlruns/artifacts").resolve())
    legacy_prefix = str((repository_root / "mlartifacts").resolve())
    source_prefix = str(repository_root.resolve()) + "/"
    connection = sqlite3.connect(database)
    try:
        connection.execute("begin")
        connection.execute(
            "update experiments set artifact_location="
            "replace(replace(artifact_location, ?, 'mlflow-artifacts:'), ?, 'mlflow-artifacts:')",
            (artifact_prefix, legacy_prefix),
        )
        connection.execute(
            "update runs set artifact_uri="
            "replace(replace(artifact_uri, ?, 'mlflow-artifacts:'), ?, 'mlflow-artifacts:'), "
            "user_id='release-builder'",
            (artifact_prefix, legacy_prefix),
        )
        connection.execute(
            "update model_versions set source=replace(source, ?, 'mlflow-artifacts:'), "
            "storage_location=replace(storage_location, ?, 'mlflow-artifacts:'), "
            "user_id='release-builder'",
            (artifact_prefix, artifact_prefix),
        )
        connection.execute(
            "update tags set value=replace(value, ?, '') where value like ?",
            (source_prefix, source_prefix + "%"),
        )
        connection.execute(
            "update tags set value='release-builder' where key='mlflow.user'"
        )
        connection.execute(
            "update logged_models set artifact_location="
            "replace(artifact_location, ?, 'mlflow-artifacts:')",
            (artifact_prefix,),
        )
        connection.execute(
            "update logged_model_tags set tag_value=replace(tag_value, ?, '') "
            "where tag_value like ?",
            (source_prefix, source_prefix + "%"),
        )
        connection.execute(
            "update logged_model_tags set tag_value='release-builder' "
            "where tag_key='mlflow.user'"
        )
        connection.commit()
        connection.execute("vacuum")
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", default=".")
    args = parser.parse_args()
    repository_root = Path(args.repository_root).resolve()
    registry = repository_root / "mlruns"

    sanitize_database(registry / "mlflow.db", repository_root)
    for mlmodel in registry.glob("artifacts/**/MLmodel"):
        sanitize_mlmodel(mlmodel)
    for pickle_path in registry.glob("artifacts/**/python_model.pkl"):
        sanitize_pyfunc_pickle(pickle_path)

    print("Portable MLflow registry sanitation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
