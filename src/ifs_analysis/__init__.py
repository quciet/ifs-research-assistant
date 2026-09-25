"""Verified saved-result access; no model execution or model-provider dependency."""
__version__ = "0.1.0"
from .reader import Reader, Selection
from .analysis import check_equality, rank_gdp, reconcile_investment
from .registry import Registry
from .errors import AnalysisError
