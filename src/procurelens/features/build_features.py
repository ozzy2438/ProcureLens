"""Feature engineering for both models, reading from dbt marts.

Amendment risk features (per contract at award time):
- agency, UNSPSC category, procurement method, confidentiality flags
- contract duration, initial value band, end-of-financial-year award flag
- supplier history: prior contract count, prior amendment rate, agency familiarity

Fit scorer features (per open tender):
- category match vs firm capability profile, agency spend momentum,
  typical award size, incumbent concentration (HHI), panel vs open approach
"""
from __future__ import annotations

import pandas as pd


def build_amendment_features(contracts: pd.DataFrame) -> pd.DataFrame:
    """Return model-ready feature frame; target = was_amended_up (bool)."""
    # TODO(week-2)
    raise NotImplementedError


def build_fit_features(tenders: pd.DataFrame, capability_profile: dict) -> pd.DataFrame:
    # TODO(week-3)
    raise NotImplementedError
