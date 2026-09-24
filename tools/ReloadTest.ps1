# ============================================================
#  HMI Reload Consistency Test   (docs/04 3.0, Rule 52 / 72)
#
#  Where to run it: anywhere. The script finds the log folder itself -
#  it looks in the current directory first, then at every MT5 data folder
#  under %APPDATA%\MetaQuotes\Terminal\<ID>\MQL5\Logs and picks the one
#  with the most recent .log. Override with  -LogDir "D:\...\MQL5\Logs".
#
#  If PowerShell refuses to run it:  Set-ExecutionPolicy -Scope Process Bypass
#  Call it by full path if you are not in its folder, e.g.
#     & "$env:USERPROFILE\Desktop\ReloadTest.ps1" -Days 5
#
#  Usage:  -Source is OPTIONAL. Without it, every chart found in the log
#          is processed - which also avoids guessing broker symbol suffixes
#          (EURUSD.a / EURUSDm / EURUSD#).
#
#     .\ReloadTest.ps1 -Live                 how many LIVE marks each chart has
#                                            so far (the wait-for-samples check)
#     .\ReloadTest.ps1                       list the charts and their blocks
#     .\ReloadTest.ps1 -LiveVsBuild          future-leak test, all charts
#     .\ReloadTest.ps1 -Rejects              Rule 6 refusals, all charts
#     .\ReloadTest.ps1 -Ctx                  H4 context events + the strength
#                                            distribution the panel bands on
#     .\ReloadTest.ps1 -Source "USDJPY,M5"   repaint test on that one chart
#
#     add  -Days 5  to merge the 5 most recent log files. MT5 starts a NEW
#     log file every day: a live run that spans days leaves its marks in
#     yesterday's file while today's reload writes into today's, and reading
#     only the newest would silently see none of them.
#
#  Several charts each run their own instance and write into the SAME log,
#  so blocks interleave. Comparing across sources would be meaningless -
#  hence the grouping below.
# ============================================================
param([string]$Source = "", [switch]$LiveVsBuild, [switch]$Rejects, [switch]$Live,
      [switch]$Ctx, [int]$Days = 1, [string]$LogDir = "")

# Row layout after the tag is stripped:
#   0 symbol  1 "MODEL"  2 dir  3 cycle_id  4 block_id  5 anchor  6 model
#   7 confirm_time  8 price  9 ref_time  10 ref_level
# Columns 3 and 4 are init-relative sequence numbers - see -LiveVsBuild below.
function Key([string]$row) {
    $c = $row -split ','
    if ($c.Count -lt 6) { return $row }
    (@($c[0..2]) + @($c[5..($c.Count-1)])) -join ','
}

# Finding the folder by hand is the single most common way to lose an hour
# with this script: PowerShell opens in %USERPROFILE%, MT5 keeps its logs
# under a hashed terminal id, and there are TWO Logs folders per terminal -
# \logs (the journal) and \MQL5\Logs (what Print writes). So look instead.
function Find-LogDir {
    if ($LogDir) {
        if (-not (Test-Path $LogDir)) { Write-Host "-LogDir not found: $LogDir" -ForegroundColor Red; exit }
        return (Resolve-Path $LogDir).Path
    }
    if (Get-ChildItem -Path . -Filter *.log -ErrorAction SilentlyContinue) { return (Get-Location).Path }

    $base = Join-Path $env:APPDATA 'MetaQuotes\Terminal'
    if (-not (Test-Path $base)) { return $null }
    $cands = Get-ChildItem $base -Directory -ErrorAction SilentlyContinue |
             ForEach-Object { Join-Path $_.FullName 'MQL5\Logs' } |
             Where-Object   { Test-Path $_ } |
             ForEach-Object {
                 $newest = Get-ChildItem $_ -Filter *.log -ErrorAction SilentlyContinue |
                           Sort-Object LastWriteTime | Select-Object -Last 1
                 if ($newest) { [pscustomobject]@{ Dir = $_; When = $newest.LastWriteTime } }
             }
    if (-not $cands) { return $null }
    ($cands | Sort-Object When | Select-Object -Last 1).Dir
}

$dir = Find-LogDir
if (-not $dir) {
    Write-Host "`ncould not find any MQL5\Logs folder with a .log in it." -ForegroundColor Red
    Write-Host "In MT5: File -> Open Data Folder, then go into MQL5\Logs," -ForegroundColor Yellow
    Write-Host "copy that path and pass it:  -LogDir `"<path>`"" -ForegroundColor Yellow
    Write-Host "NOTE the MQL5\ part - the \logs folder next to it is the journal," -ForegroundColor Yellow
    Write-Host "not what the indicator's Print writes to." -ForegroundColor Yellow
    exit
}
Write-Host "log folder : $dir" -ForegroundColor Cyan

$logs = Get-ChildItem -Path $dir -Filter *.log | Sort-Object LastWriteTime | Select-Object -Last $Days
if (-not $logs) { Write-Host "no .log file in $dir" -ForegroundColor Red; exit }
Write-Host "log file(s): $(($logs | ForEach-Object Name) -join ', ')" -ForegroundColor Cyan

# Oldest first, so LIVE rows keep their real order relative to the rebuild.
$all = @()
foreach ($f in $logs) { $all += Get-Content $f.FullName }
# -Live is the check you run while waiting for samples: it needs no build
# block and no -Source, and it discovers the charts from the log itself, so
# adding symbols does not mean editing a list.
if ($Live) {
    $tally = @{}
    foreach ($l in $all) {
        if ($l -notmatch 'HMI-(LIVE|BUILD),') { continue }
        $src = if ($l -match '\(([A-Za-z0-9._#]+,[A-Za-z0-9]+)\)') { $Matches[1] } else { '?' }
        if (-not $tally.ContainsKey($src)) { $tally[$src] = 0 }
        if ($l -match 'HMI-LIVE,') { $tally[$src]++ }
    }
    if ($tally.Count -eq 0) {
        Write-Host "`nno HMI rows at all. Is InpLogSignals = true ?" -ForegroundColor Red
        exit
    }
    Write-Host "`nLIVE marks so far:`n" -ForegroundColor Cyan
    $total = 0
    foreach ($k in ($tally.Keys | Sort-Object)) {
        $n = $tally[$k]; $total += $n
        Write-Host ("  {0,-14} {1,5}" -f $k, $n) -ForegroundColor $(if ($n -gt 0) { 'Green' } else { 'DarkGray' })
    }
    Write-Host ("`n  total {0}" -f $total)
    if ($total -eq 0) {
        Write-Host "`nnothing yet. Leave the charts running and do NOT reload them." -ForegroundColor Yellow
    } else {
        Write-Host "`nnow reload each chart once (switch timeframe away and back)," -ForegroundColor Yellow
        Write-Host "then run:  .\ReloadTest.ps1 -LiveVsBuild -Days $Days" -ForegroundColor Yellow
    }
    exit
}

# -Ctx: the Context chain had no auditable output at all until HMI-CTX, so
# `str N` on the panel could not be checked or put in perspective. This reads
# those rows, dedupes across rebuilds, and reports where the current strength
# sits in that chart's own history - the numbers the panel bands on, measured
# rather than invented.
if ($Ctx) {
    $rows = @()
    foreach ($l in $all) {
        if ($l -notmatch 'HMI-CTX,(.*)$') { continue }
        $c = $Matches[1] -split ','
        if ($c.Count -lt 11) { continue }
        $f = @{}
        foreach ($p in $c[2..($c.Count-1)]) { $kv = $p -split '=', 2; if ($kv.Count -eq 2) { $f[$kv[0]] = $kv[1] } }
        $rows += [pscustomobject]@{
            Sym = $c[0]; Kind = $c[1]; Dir = $f['dir']; Live = $f['live']
            Ctx = $f['ctx']; Str = [int]$f['str']; Messy = $f['messy']
            Bar = $f['bar']; Swing = $f['swing']; Raw = $Matches[1]
            Key = "$($c[0])|$($c[1])|$($f['bar'])|$($f['swing'])"
        }
    }
    if ($rows.Count -eq 0) {
        Write-Host "`nno HMI-CTX rows. Need v2.33+ installed with InpLogSignals = true." -ForegroundColor Red
        exit
    }
    # One event is re-emitted by every rebuild; bar+swing identify it.
    $rows = $rows | Group-Object Key | ForEach-Object { $_.Group[0] }
    Write-Host "`n$($rows.Count) distinct context events`n" -ForegroundColor Cyan

    foreach ($g in ($rows | Group-Object Sym | Sort-Object Name)) {
        Write-Host ("  {0}" -f $g.Name) -ForegroundColor White
        foreach ($k in ($g.Group | Group-Object Kind | Sort-Object Name)) {
            Write-Host ("      {0,-14} {1,4}" -f $k.Name, $k.Count)
        }
        # Strength is sampled at each BOS: the value that break left behind.
        $sv = @($g.Group | Where-Object Kind -eq 'BOS' | ForEach-Object { $_.Str } | Sort-Object)
        if ($sv.Count -ge 5) {
            function Pct([int[]]$a, [double]$p) { $a[[int][Math]::Floor(($a.Count - 1) * $p)] }
            $cur = ($g.Group | Sort-Object Bar | Select-Object -Last 1).Str
            Write-Host ("      strength  n={0}  min={1}  P33={2}  median={3}  P67={4}  P90={5}  max={6}   latest={7}" -f `
                        $sv.Count, $sv[0], (Pct $sv 0.33), (Pct $sv 0.50), (Pct $sv 0.67), (Pct $sv 0.90), $sv[-1], $cur) -ForegroundColor Green
            $below = @($sv | Where-Object { $_ -lt $cur }).Count
            Write-Host ("      latest {0} sits above {1}% of this chart's own history" -f $cur, [int](100.0 * $below / $sv.Count)) -ForegroundColor Green
        } else {
            Write-Host "      strength  too few BOS samples yet" -ForegroundColor DarkGray
        }
    }
    $out = Join-Path $dir "ctx_events.csv"
    $rows | Select-Object Sym, Kind, Dir, Live, Ctx, Str, Messy, Bar, Swing |
            Sort-Object Sym, Bar | Export-Csv -NoTypeInformation -Encoding UTF8 $out
    Write-Host "`nwritten to $out" -ForegroundColor Green
    exit
}

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

# Which charts to work on. Naming one by hand is a trap of its own: brokers
# suffix their symbols (EURUSD.a, EURUSDm, EURUSD#), so a guessed -Source
# silently matches nothing. With no -Source, do every chart that is present.
$targets = if ($Source -ne "") { @($Source) } else { @($sources | ForEach-Object Name) }
if ($Source -ne "" -and $sources.Name -notcontains $Source) {
    Write-Host "`n'$Source' is not one of the sources above." -ForegroundColor Red
    Write-Host "copy the name exactly as listed, or drop -Source to do all of them." -ForegroundColor Yellow
    exit
}

function Show-Rejects([string]$src) {
    # The accept side (POI-02a) is proved by a POI that exists. The refusal
    # side needs the pairs that were thrown away - a counter cannot be
    # checked against the chart, a printed gap can.
    $rej = @()
    foreach ($l in $all) {
        $s2 = if ($l -match '\(([A-Za-z0-9._#]+,[A-Za-z0-9]+)\)') { $Matches[1] } else { '?' }
        if ($s2 -eq $src -and $l -match 'HMI-REJECT,(.*)$') { $rej += $Matches[1] }
    }
    Write-Host "`n--- $src : Rule 6 refusals (H4 POI) ---" -ForegroundColor Cyan
    if ($rej.Count -eq 0) {
        Write-Host "  none - every H4 FVG here found a connected OB (or InpLogSignals is off)." -ForegroundColor Yellow
        return
    }
    $rej = @($rej | Select-Object -Unique)
    Write-Host "  $($rej.Count) refused FVG(s)`n"
    $rej | ForEach-Object { Write-Host "  $_" }
    $out = Join-Path $dir ("poi_rejects_" + ($src -replace '[^A-Za-z0-9]','_') + ".txt")
    $rej | Set-Content $out
    Write-Host "`n  written to $out" -ForegroundColor Green
}

function Show-LiveVsBuild([string]$src) {
    # A reload test cannot see a future leak: a leaking build re-reads the
    # same future bars every time and stays self-consistent. Live rows were
    # emitted bar by bar with only the past available, so a mark that does
    # not survive into the rebuild - or changes - is the real signal.
    $live = @()
    foreach ($l in $raw) {
        $s2 = if ($l -match '\(([A-Za-z0-9._#]+,[A-Za-z0-9]+)\)') { $Matches[1] } else { '?' }
        if ($s2 -eq $src -and $l -match 'HMI-LIVE,(.*)$') { $live += $Matches[1] }
    }
    $sel2 = @($blocks | Where-Object { $_.Src -eq $src })
    Write-Host "`n--- $src : LIVE vs BUILD ---" -ForegroundColor Cyan
    if ($sel2.Count -lt 1) { Write-Host "  no build block for this chart." -ForegroundColor Red; return }
    $build = $sel2[-1].Rows
    Write-Host "  live rows  : $($live.Count)"
    Write-Host "  build rows : $($build.Count)  ($($sel2[-1].Head))"
    if ($live.Count -eq 0) {
        Write-Host "  no HMI-LIVE rows yet. Leave the chart running until new marks" -ForegroundColor Yellow
        Write-Host "  confirm live, then reload once and run this again." -ForegroundColor Yellow
        return
    }
    # cycle_id / block_id are g_next_id sequence numbers, reset to 1 on every
    # init. A live session keeps appending to the window it started with; a
    # rebuild takes the most recent 5000 M5 bars, so the oldest bars - and the
    # ids allocated in them - are gone, and every later id shifts down. Those
    # two columns therefore CANNOT match across live and rebuild, and comparing
    # whole rows would report a future leak that is only renumbering.
    # The event's identity is the rest: dir, anchor, model, confirm time,
    # price, reference time and level.
    $liveKey  = @{}
    foreach ($r in $live)  { $liveKey[(Key $r)] = $r }
    $buildKey = @{}
    foreach ($r in $build) { $buildKey[(Key $r)] = $r }

    $missing = @($liveKey.Keys | Where-Object { -not $buildKey.ContainsKey($_) })
    Write-Host "  distinct live marks : $($liveKey.Count)   (ids ignored)"
    if ($missing.Count -eq 0) {
        Write-Host "  ALL $($liveKey.Count) LIVE MARKS SURVIVED THE REBUILD." -ForegroundColor Green
        Write-Host "  every field but the sequence ids is identical - no sign of a future leak." -ForegroundColor Green
    } else {
        Write-Host "  $($missing.Count) LIVE mark(s) do NOT appear in the rebuild:" -ForegroundColor Red
        $missing | Select-Object -First 20 | ForEach-Object { Write-Host "    $($liveKey[$_])" }
        $out = Join-Path $dir ("live_vs_build_diff_" + ($src -replace '[^A-Za-z0-9]','_') + ".txt")
        $missing | ForEach-Object { $liveKey[$_] } | Set-Content $out
        Write-Host "  written to $out" -ForegroundColor Red
        Write-Host "  check the oldest one first: if it predates the rebuild window" -ForegroundColor Yellow
        Write-Host "  (see from= in the BEGIN line) it simply aged out - not a leak." -ForegroundColor Yellow
    }
}

function Show-Reload([string]$src) {
    $sel = @($blocks | Where-Object { $_.Src -eq $src })
    Write-Host "`n--- $src : comparing the last two builds ---" -ForegroundColor Cyan
    if ($sel.Count -lt 2) {
        Write-Host "  only $($sel.Count) block(s); 2 are needed." -ForegroundColor Red
        Write-Host "  force a rebuild on THAT chart: switch timeframe away and back." -ForegroundColor Yellow
        return
    }
    $A = $sel[-2]; $B = $sel[-1]
    Write-Host "  run1 $($A.Head)"
    Write-Host "  run2 $($B.Head)"
    if ($A.Head -ne $B.Head) {
        Write-Host "  WINDOW MOVED between runs - differences at the OLDEST edge are expected," -ForegroundColor Yellow
        Write-Host "  anywhere else is not." -ForegroundColor Yellow
    }
    $diff = Compare-Object $A.Rows $B.Rows
    if (-not $diff) {
        Write-Host "  IDENTICAL - $($A.Rows.Count) rows match exactly. No repaint." -ForegroundColor Green
    } elseif (-not (Compare-Object ($A.Rows | ForEach-Object { Key $_ }) ($B.Rows | ForEach-Object { Key $_ }))) {
        # Every event matches once the sequence ids are set aside. That is
        # renumbering, not a repaint: the window slid, an id-allocating event
        # dropped off the oldest edge, and every later id shifted down.
        Write-Host "  IDENTICAL apart from cycle_id / block_id - $($A.Rows.Count) rows." -ForegroundColor Green
        Write-Host "  the window moved and the sequence ids renumbered. No repaint." -ForegroundColor Green
    } else {
        Write-Host "  DIFFERENCES: $($diff.Count) of $($A.Rows.Count) rows" -ForegroundColor Red
        $diff | Select-Object -First 40 | Format-Table SideIndicator, InputObject -AutoSize
        $out = Join-Path $dir ("reload_diff_" + ($src -replace '[^A-Za-z0-9]','_') + ".txt")
        $diff | ForEach-Object { "{0} {1}" -f $_.SideIndicator, $_.InputObject } | Set-Content $out
        Write-Host "  full diff written to $out" -ForegroundColor Red
    }
}

if (-not $LiveVsBuild -and -not $Rejects -and $Source -eq "") {
    Write-Host "`nnothing asked for. Add one of:" -ForegroundColor Yellow
    Write-Host "  -Live          how many LIVE marks so far (no reload needed)" -ForegroundColor Yellow
    Write-Host "  -LiveVsBuild   future-leak test  (all charts above, or one via -Source)" -ForegroundColor Yellow
    Write-Host "  -Rejects       Rule 6 refusals   (POI-02b)" -ForegroundColor Yellow
    Write-Host "  -Ctx           context events + strength distribution" -ForegroundColor Yellow
    Write-Host "  -Source `"<name>`"   repaint test on that one chart" -ForegroundColor Yellow
    exit
}

foreach ($t in $targets) {
    if     ($Rejects)     { Show-Rejects      $t }
    elseif ($LiveVsBuild) { Show-LiveVsBuild  $t }
    else                  { Show-Reload       $t }
}
