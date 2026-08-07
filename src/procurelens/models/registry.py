"""MLflow registry helpers (lazy imports so core install stays light)."""
from __future__ import annotations

from typing import Any


def load_champion(model_name: str) -> Any:
    """Load the model version tagged with alias 'champion'."""
    import mlflow

    return mlflow.pyfunc.load_model(f"models:/{model_name}@champion")
