from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import DefaultDict, Dict, Tuple

from app.core.model_gateway.observability.config import ObservabilityConfig
from app.core.model_gateway.observability.events import StandardCallEvent


@dataclass
class _LatencyStats:
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    def record(self, ms: float) -> None:
        self.count += 1
        self.total_ms += ms
        if ms > self.max_ms:
            self.max_ms = ms

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count else 0.0


@dataclass
class MetricsSnapshot:
    requests_total: int = 0
    errors_total: int = 0
    tokens_input_total: int = 0
    tokens_output_total: int = 0
    cost_total: float = 0.0
    latency_by_key: Dict[str, _LatencyStats] = field(default_factory=dict)


class MetricsRegistry:
    """In-process metrics collector (LiteLLM prometheus.py-inspired labels)."""

    def __init__(self, config: ObservabilityConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._requests: DefaultDict[Tuple[str, str], int] = defaultdict(int)
        self._errors: DefaultDict[Tuple[str, str], int] = defaultdict(int)
        self._tokens_in: DefaultDict[Tuple[str, str], int] = defaultdict(int)
        self._tokens_out: DefaultDict[Tuple[str, str], int] = defaultdict(int)
        self._cost: DefaultDict[Tuple[str, str], float] = defaultdict(float)
        self._latency: DefaultDict[Tuple[str, str], _LatencyStats] = defaultdict(_LatencyStats)

    def _key(self, provider: str, model: str) -> Tuple[str, str]:
        return (provider or "unknown", model or "unknown")

    def record_event(self, event: StandardCallEvent) -> None:
        if not self._config.metrics_enabled:
            return
        provider = event.resolved_provider or event.provider or "unknown"
        model = event.resolved_model or event.model or "unknown"
        key = self._key(provider, model)
        with self._lock:
            self._requests[key] += 1
            if not event.success:
                self._errors[key] += 1
            if event.latency_ms is not None:
                self._latency[key].record(event.latency_ms)
            if event.tokens_input is not None:
                self._tokens_in[key] += int(event.tokens_input)
            if event.tokens_output is not None:
                self._tokens_out[key] += int(event.tokens_output)
            if event.cost is not None:
                self._cost[key] += float(event.cost)

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            snap = MetricsSnapshot()
            snap.requests_total = sum(self._requests.values())
            snap.errors_total = sum(self._errors.values())
            snap.tokens_input_total = sum(self._tokens_in.values())
            snap.tokens_output_total = sum(self._tokens_out.values())
            snap.cost_total = sum(self._cost.values())
            snap.latency_by_key = dict(self._latency)
            return snap

    def inc_request(self, *, provider: str, model: str, success: bool) -> None:
        key = self._key(provider, model)
        with self._lock:
            self._requests[key] += 1
            if not success:
                self._errors[key] += 1

    def record_latency(self, *, provider: str, model: str, latency_ms: float) -> None:
        key = self._key(provider, model)
        with self._lock:
            self._latency[key].record(latency_ms)

    def record_tokens(
        self, *, provider: str, model: str, tokens_input: int, tokens_output: int
    ) -> None:
        key = self._key(provider, model)
        with self._lock:
            self._tokens_in[key] += tokens_input
            self._tokens_out[key] += tokens_output

    def record_cost(self, *, provider: str, model: str, cost: float) -> None:
        key = self._key(provider, model)
        with self._lock:
            self._cost[key] += cost
