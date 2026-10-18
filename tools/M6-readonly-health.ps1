# M6 non-invasive local status and HTTP RTT probe. Never changes settings.
# Run only when the PC is already connected to the owner's M6 Wi-Fi.
[CmdletBinding()]
param(
    [ValidateRange(3,40)] [int]$Samples = 12,
    [ValidateRange(1,5)] [int]$TimeoutSec = 3,
    [string]$OutputDirectory = (Get-Location).Path
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$uri = 'http://192.168.1.101/cgi-bin/index.cgi?id=host'
$records = New-Object System.Collections.Generic.List[object]
$version = $null; $channel = $null; $videoMode = $null; $audioMode = $null; $delayMode = $null
for ($i = 1; $i -le $Samples; $i++) {
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        # Fixed, read-only OEM endpoint. Never call set/logcat/STS/P2P/update.
        $response = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec $TimeoutSec -Method Get
        $timer.Stop()
        if ($response.StatusCode -ne 200) { throw "HTTP $($response.StatusCode)" }
        $json = $response.Content | ConvertFrom-Json
        if ($null -ne $json.PSObject.Properties['sys']) {
            $sys = $json.sys
            if ($null -ne $sys -and $null -ne $sys.PSObject.Properties['appver']) { $version = [string]$sys.appver }
        }
        if ($null -ne $json.PSObject.Properties['sig']) { $channel = [string]$json.sig }
        if ($null -ne $json.PSObject.Properties['vid']) { $videoMode = [string]$json.vid }
        if ($null -ne $json.PSObject.Properties['aud']) { $audioMode = [string]$json.aud }
        if ($null -ne $json.PSObject.Properties['delay']) { $delayMode = [string]$json.delay }
        $records.Add([pscustomobject]@{sample=$i;ok=$true;rtt_ms=[math]::Round($timer.Elapsed.TotalMilliseconds,2)})
    } catch {
        $timer.Stop()
        $records.Add([pscustomobject]@{sample=$i;ok=$false;rtt_ms=$null})
    }
    Write-Progress -Activity 'Read-only M6 diagnostic' -Status "$i / $Samples" -PercentComplete ([int](100*$i/$Samples))
    if ($i -lt $Samples) { Start-Sleep -Seconds 1 }
}
Write-Progress -Activity 'Read-only M6 diagnostic' -Completed
$ok = @($records | Where-Object { $_.ok })
$ordered = @($ok | ForEach-Object { $_.rtt_ms } | Sort-Object)
$median = $null; $p95 = $null; $max = $null
if ($ordered.Count -gt 0) {
    $median = $ordered[[int][math]::Floor(($ordered.Count - 1) * 0.50)]
    $p95 = $ordered[[int][math]::Ceiling(($ordered.Count - 1) * 0.95)]
    $max = $ordered[$ordered.Count - 1]
}
$report = [ordered]@{
    report_type = 'm6_http_host_rtt_readonly_v1'
    created_local = (Get-Date).ToString('s')
    source = 'GET /cgi-bin/index.cgi?id=host only'
    samples = $Samples
    successes = $ok.Count
    failures = $Samples - $ok.Count
    failure_percent = [math]::Round(100*($Samples-$ok.Count)/$Samples,1)
    http_rtt_median_ms = $median
    http_rtt_p95_ms = $p95
    http_rtt_max_ms = $max
    installed_version = $version
    wifi_ap_setting = $channel
    video_setting = $videoMode
    audio_setting = $audioMode
    delay_setting = $delayMode
    rtt_is_not_carplay_latency = $true
    only_allowlisted_nonidentifying_fields_saved = $true
    device_configuration_changed = $false
    individual_http_samples = @($records)
}
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$file = Join-Path $OutputDirectory ("M6-health-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
$report | ConvertTo-Json -Depth 5 | Out-File -LiteralPath $file -Encoding UTF8
Write-Output "Results: $($ok.Count)/$Samples OK; HTTP RTT median=$median ms, p95=$p95 ms; saved: $file"
Write-Output 'Note: HTTP RTT is not video latency or CarPlay frame rate; no settings or flash were changed.'
