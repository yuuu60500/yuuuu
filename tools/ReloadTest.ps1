# ============================================================
#  HMI Reload Consistency Test   (docs/04 3.0, Rule 52 / 72)
#
#  Run from  <data folder>\MQL5\Logs
#     type  powershell  in the Explorer address bar
#     then  Set-ExecutionPolicy -Scope Process Bypass
#
#  Usage:
#     .\ReloadTest.ps1                       list sources and their blocks
#     .\ReloadTest.ps1 -Source "USDJPY,M5"   compare the last two blocks
#                                            of ONE chart
#
#  Several charts each run their own instance and write into the SAME log,
#  so blocks interleave. Comparing across sources would be meaningless -
#  hence the grouping below.
# ============================================================
param([string]$Source = "")

$log = Get-ChildItem *.log | Sort-Object LastWriteTime | Select-Object -Last 1
Write-Host "log file : $($log.Name)" -ForegroundColor Cyan

$raw = Get-Content $log.FullName | Where-Object { $_ -match 'HMI-BUILD' }
if ($raw.Count -eq 0) {
    Write-Host "`nno HMI-BUILD lines found." -ForegroundColor Red
    Write-Host "set InpLogSignals = true on the chart you want to test." -ForegroundColor Yellow
    exit
}

# MT5 prefixes every line with wall-clock time and the source tag:
#   2026.09.23 01:06:17.843  H4M5_Identification (USDJPY,M5)  HMI-BUILD,...
# The timestamp differs between runs, so only the payload is compared.
$blocks = @()
$open   = @{}
foreach ($l in $raw) {
    $src = if ($l -match '\(([A-Za-z0-9._#]+,[A-Za-z0-9]+)\)') { $Matches[1] } else { '?' }
    if     ($l -match 'HMI-BUILD-BEGIN,(.*)$') { $open[$src] = [pscustomobject]@{ Src=$src; Head=$Matches[1]; Rows=@(); Tail='' } }
    elseif ($l -match 'HMI-BUILD-END,(.*)$')   { if ($open[$src]) { $open[$src].Tail=$Matches[1]; $blocks+=$open[$src]; $open.Remove($src) } }
    elseif ($l -match 'HMI-BUILD,(.*)$')       { if ($open[$src]) { $open[$src].Rows += $Matches[1] } }
}

$sources = $blocks | Group-Object Src
Write-Host "`nsources found: $($sources.Count)`n" -ForegroundColor Cyan
foreach ($g in $sources) {
    Write-Host ("  {0}  -> {1} block(s)" -f $g.Name, $g.Count) -ForegroundColor White
    $i = 0
    foreach ($b in $g.Group) { Write-Host ("      [{0}] rows={1}  {2}" -f $i, $b.Rows.Count, $b.Head); $i++ }
}

if ($Source -eq "") {
    Write-Host "`npick one chart, e.g.:  .\ReloadTest.ps1 -Source `"USDJPY,M5`"" -ForegroundColor Yellow
    exit
}

$sel = $blocks | Where-Object { $_.Src -eq $Source }
if ($sel.Count -lt 2) {
    Write-Host "`n'$Source' has $($sel.Count) block(s); 2 are needed." -ForegroundColor Red
    Write-Host "force a rebuild on THAT chart: switch timeframe away and back." -ForegroundColor Yellow
    exit
}

$A = $sel[-2]; $B = $sel[-1]
Write-Host "`n--- $Source : comparing the last two builds ---" -ForegroundColor Cyan
Write-Host "  run1 $($A.Head)"
Write-Host "  run2 $($B.Head)"

if ($A.Head -ne $B.Head) {
    Write-Host "`nWINDOW MOVED between runs - differences at the OLDEST edge are expected," -ForegroundColor Yellow
    Write-Host "anywhere else is not." -ForegroundColor Yellow
}

$diff = Compare-Object $A.Rows $B.Rows
if (-not $diff) {
    Write-Host "`nIDENTICAL - $($A.Rows.Count) rows match exactly. No repaint." -ForegroundColor Green
} else {
    Write-Host "`nDIFFERENCES: $($diff.Count) of $($A.Rows.Count) rows" -ForegroundColor Red
    $diff | Select-Object -First 40 | Format-Table SideIndicator, InputObject -AutoSize
    $diff | ForEach-Object { "{0} {1}" -f $_.SideIndicator, $_.InputObject } | Set-Content reload_diff.txt
    Write-Host "full diff written to reload_diff.txt" -ForegroundColor Red
}
