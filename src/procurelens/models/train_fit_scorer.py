"""Train the Opportunity Fit Scorer (0-100 winnability score for open tenders)."""
from __future__ import annotations

REGISTERED_MODEL = "procurelens-fit-scorer"


def train() -> None:
    # TODO(week-3): LightGBM/XGBoost ranker or calibrated classifier over
    # historical award outcomes vs capability profile; export score bands.
    raise NotImplementedError


if __name__ == "__main__":
    train()
