# Metrics registry

In-process counters and latency stats keyed by `(provider, model)`. Updated on every observed completion when `METRICS_ENABLED=true`.

```python
from model_gateway.observability.manager import get_manager
snap = get_manager().metrics.snapshot()
```

Reference: `litellm/integrations/prometheus.py` (labeling patterns)
