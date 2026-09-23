# ============================================================
#  HMI Reload Consistency Test   (docs/04 §3, Rule 52 / 72)
#  Run from  <data folder>\MQL5\Logs
#     Shift + right click -> Open PowerShell window here
#
#  Usage:
#     .\ReloadTest.ps1              list the build blocks
#     .\ReloadTest.ps1 -Compare     compare the last two blocks
# ============================================================
param([switch]$Compare)

$log = Get-ChildItem *.log | Sort-Object LastWriteTime | Select-Object -Last 1
Write-Host "log file : $($log.Name)" -ForegroundColor Cyan

# Strip MT5's timestamp prefix: it is wall-clock and differs between runs,
# so comparing whole lines would flag every row as a false positive.
$lines = Get-Content $log.FullName | Where-Object { $_ -match 'HMI-BUILD' }
if ($lines.Count -eq 0) { Write-Host "no HMI-BUILD lines. Is InpLogSignals = true?" -ForegroundColor Red; exit }

$blocks = @()
$cur    = $null
foreach ($l in $lines) {
    if ($l -match 'HMI-BUILD-BEGIN,(.*)$') {
        $cur = [pscustomobject]@{ Head=$Matches[1]; Rows=@(); Tail='' }
    } elseif ($l -match 'HMI-BUILD-END,(.*)$') {
        if ($cur) { $cur.Tail = $Matches[1]; $blocks += $cur; $cur = $null }
    } elseif ($cur -and $l -match 'HMI-BUILD,(.*)$') {
        $cur.Rows += $Matches[1]
    }
}

Write-Host "`nbuild blocks found: $($blocks.Count)`n" -ForegroundColor Cyan
for ($i=0; $i -lt $blocks.Count; $i++) {
    Write-Host ("[{0}] rows={1}" -f $i, $blocks[$i].Rows.Count)
    Write-Host ("     BEGIN {0}" -f $blocks[$i].Head)
    Write-Host ("     END   {0}" -f $blocks[$i].Tail)
}

if (-not $Compare) { Write-Host "`nrun again with -Compare after reloading the indicator." -ForegroundColor Yellow; exit }

if ($blocks.Count -lt 2) { Write-Host "`nneed at least 2 blocks. Force a rebuild (see docs/04)." -ForegroundColor Red; exit }

$A = $blocks[-2]; $B = $blocks[-1]
Write-Host "`n--- comparing block $($blocks.Count-2) vs $($blocks.Count-1) ---" -ForegroundColor Cyan

if ($A.Head -ne $B.Head) {
    Write-Host "WINDOW MOVED between runs:" -ForegroundColor Yellow
    Write-Host "  run1 $($A.Head)"
    Write-Host "  run2 $($B.Head)"
    Write-Host "  differences at the OLDEST edge are expected; anywhere else is not." -ForegroundColor Yellow
}

$diff = Compare-Object $A.Rows $B.Rows
if (-not $diff) {
    Write-Host "`nIDENTICAL - $($A.Rows.Count) rows match exactly. No repaint." -ForegroundColor Green
} else {
    Write-Host "`nDIFFERENCES: $($diff.Count)" -ForegroundColor Red
    $diff | Select-Object -First 40 | Format-Table SideIndicator, InputObject -AutoSize
    $diff | ForEach-Object { $_.InputObject } | Set-Content reload_diff.txt
    Write-Host "full diff written to reload_diff.txt" -ForegroundColor Red
}
