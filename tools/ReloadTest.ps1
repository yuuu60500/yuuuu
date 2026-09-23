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
#                                            of ONE chart  (repaint test)
#     .\ReloadTest.ps1 -Source "USDJPY,M5" -LiveVsBuild
#                                            every mark emitted LIVE must
#                                            reappear identically in the
#                                            rebuild  (future-leak test)
#     .\ReloadTest.ps1 -Source "USDJPY,M5" -Rejects
#                                            list the H4 POI candidates that
#                                            Rule 6 REFUSED, with the measured
#                                            gap  (refusal-side test, POI-02b)
#
#  Several charts each run their own instance and write into the SAME log,
#  so blocks interleave. Comparing across sources would be meaningless -
#  hence the grouping below.
# ============================================================
param([string]$Source = "", [switch]$LiveVsBuild, [switch]$Rejects)

$log = Get-ChildItem *.log | Sort-Object LastWriteTime | Select-Object -Last 1
Write-Host "log file : $($log.Name)" -ForegroundColor Cyan

$all = Get-Content $log.FullName
$raw = $all | Where-Object { $_ -match 'HMI-BUILD' }
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
    Write-Host "add -LiveVsBuild for the future-leak test, -Rejects for Rule 6 refusals." -ForegroundColor Yellow
    exit
}

if ($Rejects) {
    # The accept side (POI-02) is proved by a POI that exists. The refusal
    # side needs the pairs that were thrown away - a counter cannot be
    # checked against the chart, a printed gap can.
    $rej = @()
    foreach ($l in $all) {
        $src = if ($l -match '\(([A-Za-z0-9._#]+,[A-Za-z0-9]+)\)') { $Matches[1] } else { '?' }
        if ($src -eq $Source -and $l -match 'HMI-REJECT,(.*)$') { $rej += $Matches[1] }
    }
    Write-Host "`n--- $Source : Rule 6 refusals (H4 POI) ---" -ForegroundColor Cyan
    if ($rej.Count -eq 0) {
        Write-Host "`nno HMI-REJECT lines for this chart." -ForegroundColor Yellow
        Write-Host "either every H4 FVG found a connected OB, or InpLogSignals is off." -ForegroundColor Yellow
        exit
    }
    $rej = $rej | Select-Object -Unique
    Write-Host "  $($rej.Count) refused FVG(s)`n"
    $rej | ForEach-Object { Write-Host "  $_" }
    $rej | Set-Content poi_rejects.txt
    Write-Host "`nwritten to poi_rejects.txt" -ForegroundColor Green
    Write-Host "pick one line: open the ob= bar in the data window, confirm the" -ForegroundColor Yellow
    Write-Host "gap, and confirm NO POI rectangle was drawn at that bar." -ForegroundColor Yellow
    exit
}

if ($LiveVsBuild) {
    # A reload test cannot see a future leak: a leaking build re-reads the
    # same future bars every time and stays self-consistent. Live rows were
    # emitted bar by bar with only the past available, so a mark that does
    # not survive into the rebuild - or changes - is the real signal.
    $live = @()
    foreach ($l in $raw) {
        $src = if ($l -match '\(([A-Za-z0-9._#]+,[A-Za-z0-9]+)\)') { $Matches[1] } else { '?' }
        if ($src -eq $Source -and $l -match 'HMI-LIVE,(.*)$') { $live += $Matches[1] }
    }
    $sel2 = $blocks | Where-Object { $_.Src -eq $Source }
    if ($sel2.Count -lt 1) { Write-Host "`nno build block for '$Source'." -ForegroundColor Red; exit }
    $build = $sel2[-1].Rows

    Write-Host "`n--- $Source : LIVE vs BUILD ---" -ForegroundColor Cyan
    Write-Host "  live rows  : $($live.Count)"
    Write-Host "  build rows : $($build.Count)  ($($sel2[-1].Head))"
    if ($live.Count -eq 0) {
        Write-Host "`nno HMI-LIVE rows yet. Leave the chart running until new marks" -ForegroundColor Yellow
        Write-Host "confirm live, then reload once and run this again." -ForegroundColor Yellow
        exit
    }
    $missing = $live | Where-Object { $build -notcontains $_ }
    if (-not $missing) {
        Write-Host "`nALL $($live.Count) LIVE MARKS SURVIVED THE REBUILD, byte for byte." -ForegroundColor Green
        Write-Host "no sign of a future leak in this window." -ForegroundColor Green
    } else {
        Write-Host "`n$($missing.Count) LIVE mark(s) do NOT appear in the rebuild:" -ForegroundColor Red
        $missing | Select-Object -First 20 | ForEach-Object { Write-Host "  $_" }
        $missing | Set-Content live_vs_build_diff.txt
        Write-Host "written to live_vs_build_diff.txt" -ForegroundColor Red
    }
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
