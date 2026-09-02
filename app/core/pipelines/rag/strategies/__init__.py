"""
RAG Strategy Implementations

Strategies are imported lazily and only if their module is installed,
so subset ZIPs (e.g. naive-only) still boot.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_STRATEGY_MODULES = (
    "naive",
    "advanced",
    "hierarchical",
    "graph",
    "agentic",
    "hybrid",
    "conversational",
)

_loaded: Dict[str, Any] = {}


def _load_strategy(name: str) -> Optional[Any]:
    if name in _loaded:
        return _loaded[name]
    try:
        module = importlib.import_module(f"app.core.pipelines.rag.strategies.{name}")
        _loaded[name] = module
        return module
    except ModuleNotFoundError:
        logger.info("RAG strategy not installed: %s", name)
        _loaded[name] = None
        return None
    except Exception as exc:
        logger.warning("Failed to import RAG strategy %s: %s", name, exc)
        _loaded[name] = None
        return None


def load_available_strategies() -> List[str]:
    """Import all installed strategy modules (triggers registry registration)."""
    available = []
    for name in _STRATEGY_MODULES:
        if _load_strategy(name) is not None:
            available.append(name)
    return available


def __getattr__(name: str) -> Any:
    """Lazy attribute access for strategy class names (NaiveRAG, etc.)."""
    mapping = {
        "NaiveRAG": "naive",
        "AdvancedRAG": "advanced",
        "HierarchicalRAG": "hierarchical",
        "GraphRAG": "graph",
        "AgenticRAG": "agentic",
        "HybridRAG": "hybrid",
        "ConversationalRAG": "conversational",
    }
    if name in mapping:
        module = _load_strategy(mapping[name])
        if module is None:
            raise AttributeError(name)
        return getattr(module, name)
    raise AttributeError(name)


__all__ = [
    "NaiveRAG",
    "AdvancedRAG",
    "HierarchicalRAG",
    "GraphRAG",
    "AgenticRAG",
    "HybridRAG",
    "ConversationalRAG",
    "load_available_strategies",
]
