# Verify Jaeger Monitor (SPM) pipeline for model_gateway.
# Usage: .\model_gateway\docker\scripts\verify-jaeger-monitor.ps1

$ErrorActionPreference = "Stop"
$service = "goml-gateway"
$end = [int64]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())
$base = "http://localhost:16686/api/metrics/calls?service=$service&lookback=300000&endTs=$end"

Write-Host "Checking Jaeger metrics API..."
foreach ($kind in @("server", "consumer")) {
    $url = "$base&spanKind=$kind"
    try {
        $r = Invoke-RestMethod -Uri $url
        $points = 0
        if ($r.metrics -and $r.metrics.Count -gt 0) {
            $points = @($r.metrics[0].metricPoints).Count
        }
        Write-Host ("  spanKind={0,-8} -> {1} metric series, {2} data points" -f $kind, @($r.metrics).Count, $points)
    } catch {
        Write-Host ("  spanKind={0,-8} -> ERROR: {1}" -f $kind, $_.Exception.Message)
    }
}

Write-Host ""
Write-Host "Prometheus calls_total (should include SPAN_KIND_SERVER):"
try {
    $prom = Invoke-RestMethod "http://localhost:9090/api/v1/query?query=calls_total"
    $prom.data.result | ForEach-Object {
        Write-Host ("  service={0} span_kind={1} span_name={2}" -f $_.metric.service_name, $_.metric.span_kind, $_.metric.span_name)
    }
} catch {
    Write-Host "  Prometheus not reachable on :9090"
}

Write-Host ""
Write-Host "Open Monitor with Server span kind (required for model_gateway):"
Write-Host "  http://localhost:16686/monitor"
Write-Host ""
Write-Host "In the UI: Service = goml-gateway, Span Kind = Server (NOT Consumer)."
Write-Host "If Consumer stays selected, clear site data for localhost:16686 or use a private window."
