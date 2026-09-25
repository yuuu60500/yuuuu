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
      [switch]$Ctx, [int]$Days = 1, [string]$LogDir = "", [int]$Warmup = 100)

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
        # Prices go through InvariantCulture on purpose: on a pt-BR / de-DE
        # machine the decimal separator is a comma, and a plain [double] cast
        # would read "158.125" as 158125 - every price comparison below would
        # be silently wrong.
        $ic = [Globalization.CultureInfo]::InvariantCulture
        $swp = 0.0; $cls = 0.0
        [void][double]::TryParse([string]$f['swing_px'], [Globalization.NumberStyles]::Float, $ic, [ref]$swp)
        [void][double]::TryParse([string]$f['close'],    [Globalization.NumberStyles]::Float, $ic, [ref]$cls)
        $rows += [pscustomobject]@{
            Sym = $c[0]; Kind = $c[1]; Dir = $f['dir']; Live = $f['live']
            Ctx = $f['ctx']; Str = [int]$f['str']; Messy = $f['messy']
            Bar = $f['bar']; Swing = $f['swing']; SwPx = $swp; Close = $cls
            Raw = $Matches[1]
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
        $ev = @($g.Group | Sort-Object Bar)

        # Every CHOCH opens a TRANSITION, and a TRANSITION ends exactly one way:
        # TRANS_OK, TRANS_FAIL or TIMEOUT. So CHOCH - (OK+FAIL+TIMEOUT) must be
        # 0 or 1 (1 = one still open now). Anything else means the state
        # machine or its log lost track of a transition.
        $nCh = @($ev | Where-Object Kind -eq 'CHOCH').Count
        $nOk = @($ev | Where-Object Kind -eq 'TRANS_OK').Count
        $nFl = @($ev | Where-Object Kind -eq 'TRANS_FAIL').Count
        $nTo = @($ev | Where-Object Kind -eq 'TIMEOUT').Count
        $open = $nCh - ($nOk + $nFl + $nTo)
        $acct = "      transitions  opened {0} = ok {1} + fail {2} + timeout {3} + still open {4}" -f $nCh, $nOk, $nFl, $nTo, $open
        Write-Host $acct -ForegroundColor $(if ($open -eq 0 -or $open -eq 1) { 'Green' } else { 'Red' })

        # A-33 signature. A BOS whose level an EARLIER close in the same leg had
        # already carried price past is not a new push: it is an old swing that
        # was left unswept and is only now being counted. Legs restart on
        # anything that is not a plain continuation BOS. This sees only closes
        # at logged events, so the count is a LOWER bound.
        $stale = 0; $bosN = 0; $ext = $null; $ldir = ''
        foreach ($e in $ev) {
            if ($e.Kind -eq 'BOS' -and $e.Str -gt 1 -and $ext -ne $null -and $e.Dir -eq $ldir) {
                $bosN++
                if (($ldir -eq 'UP'   -and $e.SwPx -le $ext) -or
                    ($ldir -eq 'DOWN' -and $e.SwPx -ge $ext)) { $stale++ }
                if ($ldir -eq 'UP')   { $ext = [Math]::Max($ext, $e.Close) }
                else                  { $ext = [Math]::Min($ext, $e.Close) }
            }
            elseif ($e.Kind -eq 'BOS' -or $e.Kind -eq 'TRANS_OK' -or $e.Kind -eq 'TRANS_FAIL') {
                $ext = $e.Close; $ldir = $e.Dir       # a leg begins here
            }
            else { $ext = $null; $ldir = '' }        # CHOCH / SAMELEG / TIMEOUT
        }
        if ($bosN -gt 0) {
            Write-Host ("      A-33 stale BOS  {0} of {1} continuation BOS ({2}%) re-count a level already crossed" -f `
                        $stale, $bosN, [int](100.0 * $stale / $bosN)) -ForegroundColor $(if ($stale -gt 0) { 'Yellow' } else { 'Green' })
        }

        # Strength is sampled at each BOS: the value that break left behind.
        # NOTE: until A-33 is fixed these counts are inflated - do not set bands on them.
        $sv = @($ev | Where-Object Kind -eq 'BOS' | ForEach-Object { $_.Str } | Sort-Object)
        $last = $ev[-1]
        if ($sv.Count -ge 5) {
            function Pct([int[]]$a, [double]$p) { $a[[int][Math]::Floor(($a.Count - 1) * $p)] }
            Write-Host ("      strength  n={0}  min={1}  P33={2}  median={3}  P67={4}  P90={5}  max={6}" -f `
                        $sv.Count, $sv[0], (Pct $sv 0.33), (Pct $sv 0.50), (Pct $sv 0.67), (Pct $sv 0.90), $sv[-1]) -ForegroundColor Green
            if ($last.Ctx -eq 'BULLISH' -or $last.Ctx -eq 'BEARISH') {
                $below = @($sv | Where-Object { $_ -lt $last.Str }).Count
                Write-Host ("      now {0}  str {1}  - above {2}% of this chart's own history" -f `
                            $last.Ctx, $last.Str, [int](100.0 * $below / $sv.Count)) -ForegroundColor Green
            } else {
                Write-Host ("      now {0}  - not rated (no trend to measure)" -f $last.Ctx) -ForegroundColor DarkGray
            }
        } else {
            Write-Host "      strength  too few BOS samples yet" -ForegroundColor DarkGray
        }
    }
    $out = Join-Path $dir "ctx_events.csv"
    $rows | Select-Object Sym, Kind, Dir, Live, Ctx, Str, Messy, Bar, Swing, SwPx, Close |
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
    # A live row can only be checked against a rebuild that (a) came AFTER it,
    # (b) was made by the SAME indicator version, and (c) covers its bar.
    # Anything else is not evidence either way, and treating it as "missing"
    # reports a leak that is only ordering, an upgrade or the window sliding.
    # So walk the log in order, keeping track of which version each line of
    # this chart came from, and sort every live row into one of four piles.
    $ic  = [Globalization.CultureInfo]::InvariantCulture
    # Only a COMPLETE build counts - one whose END line has also reached the
    # log. MT5 buffers its log, so a rebuild's BEGIN can be on disk while its
    # rows and END are not yet; taking that BEGIN as "the rebuild" while the
    # rows came from the previous complete block compared a mark against a
    # build that did not contain its bar (A-35b).
    $ver = '?'; $live = @(); $lastBegin = -1; $bVer = ''; $bFrom = ''; $bTo = ''
    $pBegin = -1; $pVer = ''; $pFrom = ''; $pTo = ''
    for ($i = 0; $i -lt $all.Count; $i++) {
        $l = $all[$i]
        if ($l -notmatch '\(([A-Za-z0-9._#]+,[A-Za-z0-9]+)\)') { continue }
        if ($Matches[1] -ne $src) { continue }
        if ($l -match 'HMI v(\S+) starting on') { $ver = $Matches[1]; continue }
        if ($l -match 'HMI-BUILD-BEGIN,.*from=([0-9.: ]+),to=([0-9.: ]+)') {
            $pBegin = $i; $pVer = $ver; $pFrom = $Matches[1].Trim(); $pTo = $Matches[2].Trim(); continue
        }
        if ($l -match 'HMI-BUILD-END,') {
            if ($pBegin -ge 0) { $lastBegin = $pBegin; $bVer = $pVer; $bFrom = $pFrom; $bTo = $pTo; $pBegin = -1 }
            continue
        }
        if ($l -match 'HMI-LIVE,(.*)$') {
            $live += [pscustomobject]@{ Idx = $i; Ver = $ver; Row = $Matches[1]; Conf = (($Matches[1] -split ',')[7]) }
        }
    }
    $sel2 = @($blocks | Where-Object { $_.Src -eq $src })
    Write-Host "`n--- $src : LIVE vs BUILD ---" -ForegroundColor Cyan
    if ($sel2.Count -lt 1 -or $lastBegin -lt 0) { Write-Host "  no complete build block for this chart." -ForegroundColor Red; return }
    $build = $sel2[-1].Rows
    if ($pBegin -ge 0) {
        Write-Host "  a newer rebuild has started but its END is not in the log yet - wait a minute and rerun." -ForegroundColor Yellow
    }
    Write-Host "  rebuild    : v$bVer  from=$bFrom  to=$bTo   ($($build.Count) rows)"

    # The rebuild's last bar OPENS at `to`; a mark's printed time is its bar's
    # CLOSE. So a mark is inside the window iff its close <= to + 5 minutes.
    $edge = [datetime]::ParseExact($bTo, 'yyyy.MM.dd HH:mm', $ic).AddMinutes(5)
    $from = [datetime]::ParseExact($bFrom, 'yyyy.MM.dd HH:mm', $ic)
    $after = @(); $other = @(); $aged = @(); $ok = @()
    foreach ($r in $live) {
        $t = [datetime]::MinValue
        [void][datetime]::TryParseExact($r.Conf, 'yyyy.MM.dd HH:mm:ss', $ic, [Globalization.DateTimeStyles]::None, [ref]$t)
        if     ($r.Idx -gt $lastBegin) { $after += $r }      # emitted after this rebuild
        elseif ($r.Ver -ne $bVer)      { $other += $r }      # another version's rules
        elseif ($t -lt $from)          { $aged  += $r }      # slid out of the window
        elseif ($t -gt $edge)          { $after += $r }      # beyond the window's end
        else                           { $ok    += $r }
    }
    Write-Host ("  live rows  : {0} total  ->  comparable {1}  |  after rebuild {2}  |  other version {3}  |  aged out {4}" -f `
                $live.Count, $ok.Count, $after.Count, $other.Count, $aged.Count)
    if ($after.Count -gt 0) {
        Write-Host "  (after-rebuild rows are checked by the NEXT reload, not this one)" -ForegroundColor DarkGray
    }
    if ($ok.Count -eq 0) {
        Write-Host "  nothing comparable yet. Let live marks accumulate, THEN reload once, THEN run this." -ForegroundColor Yellow
        return
    }

    # cycle_id / block_id are init-relative sequence numbers (A-20); compare
    # the event itself.
    $buildKey = @{}
    foreach ($r in $build) { $buildKey[(Key $r)] = $r }
    $liveKey = @{}
    foreach ($r in $ok) { $liveKey[(Key $r.Row)] = $r.Row }
    $missing = @($liveKey.Keys | Where-Object { -not $buildKey.ContainsKey($_) })
    if ($missing.Count -eq 0) {
        Write-Host "  ALL $($liveKey.Count) COMPARABLE LIVE MARKS SURVIVED THE REBUILD - no sign of a future leak." -ForegroundColor Green
    } else {
        Write-Host "  $($missing.Count) comparable LIVE mark(s) do NOT appear in the rebuild:" -ForegroundColor Red
        $missing | Select-Object -First 20 | ForEach-Object { Write-Host "    $($liveKey[$_])" }
        $out = Join-Path $dir ("live_vs_build_diff_" + ($src -replace '[^A-Za-z0-9]','_') + ".txt")
        $missing | ForEach-Object { $liveKey[$_] } | Set-Content $out
        Write-Host "  written to $out" -ForegroundColor Red
        Write-Host "  same version, emitted before the rebuild, inside its window: this IS the signal." -ForegroundColor Red
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
        # Rows differ even with ids set aside. When the window moved, most of
        # that is explained by where each build STARTS, so classify every
        # difference instead of dumping the raw diff (whose ids have all
        # shifted and tell you nothing):
        #   aged out   - only in the older build, bar is before the new window
        #   warm-up    - only in the older build, inside the new build's first
        #                $Warmup bars, where it builds structure but marks nothing
        #   carried    - only in the older build, from a cycle whose first mark
        #                already falls before the new build's warm-up ended:
        #                that cycle began before the new build could see it
        #   new bars   - only in the newer build, after the older build's end
        #   LOOK       - anything else. This is where a real repaint would be.
        $ic = [Globalization.CultureInfo]::InvariantCulture
        function HeadTime([string]$h, [string]$which) {
            if ($h -match "$which=([0-9.]+ [0-9:]+)") { return [datetime]::ParseExact($Matches[1], 'yyyy.MM.dd HH:mm', $ic) }
            return [datetime]::MinValue
        }
        function RowTime([string]$r) {
            $t = [datetime]::MinValue
            [void][datetime]::TryParseExact((($r -split ',')[7]), 'yyyy.MM.dd HH:mm:ss', $ic, [Globalization.DateTimeStyles]::None, [ref]$t)
            return $t
        }
        $bFrom = HeadTime $B.Head 'from'
        $aTo   = (HeadTime $A.Head 'to').AddMinutes(5)
        $wEnd  = $bFrom.AddMinutes(5 * $Warmup)          # approximate: assumes no gap in those bars

        $ka = @{}; foreach ($r in $A.Rows) { $ka[(Key $r)] = $r }
        $kb = @{}; foreach ($r in $B.Rows) { $kb[(Key $r)] = $r }
        $first = @{}
        foreach ($r in $A.Rows) {
            $cy = ($r -split ',')[3]; $t = RowTime $r
            if (-not $first.ContainsKey($cy) -or $t -lt $first[$cy]) { $first[$cy] = $t }
        }
        # The newer build cannot have a counterpart for anything before it has
        # produced a single mark: after warm-up it still has to touch a POI,
        # open a session, form a block and ARM before any cycle exists, while
        # the older build may already be mid-cycle. Rows in that stretch are
        # 'converging'. The window is only the head of the build, so a repaint
        # in the middle still lands in LOOK.
        $bFirst = [datetime]::MaxValue
        foreach ($r in $B.Rows) { $t = RowTime $r; if ($t -gt [datetime]::MinValue -and $t -lt $bFirst) { $bFirst = $t } }

        $cls = @()
        foreach ($k in $ka.Keys) {
            if ($kb.ContainsKey($k)) { continue }
            $r = $ka[$k]; $t = RowTime $r; $cy = ($r -split ',')[3]
            $c = 'LOOK'
            if     ($t -le $bFrom)          { $c = 'aged out' }
            elseif ($t -le $wEnd)           { $c = 'warm-up' }
            elseif ($first[$cy] -le $wEnd)  { $c = 'carried' }
            elseif ($t -lt $bFirst)         { $c = 'converging' }
            $cls += [pscustomobject]@{ Side = 'old only'; Class = $c; Time = $t; Row = $r }
        }
        foreach ($k in $kb.Keys) {
            if ($ka.ContainsKey($k)) { continue }
            $r = $kb[$k]; $t = RowTime $r
            $c = 'LOOK'
            if ($t -gt $aTo) { $c = 'new bars' }
            $cls += [pscustomobject]@{ Side = 'new only'; Class = $c; Time = $t; Row = $r }
        }
        $cls = $cls | Sort-Object Time
        Write-Host ("  {0} rows differ once ids are ignored (warm-up assumed {1} bars, new warm-up ends ~{2}, newer build's first mark {3})" -f `
                    $cls.Count, $Warmup, $wEnd.ToString('yyyy.MM.dd HH:mm'), $bFirst.ToString('yyyy.MM.dd HH:mm')) -ForegroundColor Yellow
        foreach ($g in ($cls | Group-Object Class | Sort-Object Name)) {
            Write-Host ("    {0,-9} {1,4}" -f $g.Name, $g.Count) -ForegroundColor $(if ($g.Name -eq 'LOOK') { 'Red' } else { 'Green' })
        }
        $look = @($cls | Where-Object Class -eq 'LOOK')
        if ($look.Count -eq 0) {
            Write-Host "  every difference is explained by where each build starts or ends. No repaint." -ForegroundColor Green
        } else {
            Write-Host "  unexplained - inspect these:" -ForegroundColor Red
            $look | Select-Object -First 20 | ForEach-Object { Write-Host ("    {0}  {1}" -f $_.Side, $_.Row) }
        }
        $out = Join-Path $dir ("reload_diff_" + ($src -replace '[^A-Za-z0-9]','_') + ".txt")
        $cls | ForEach-Object { "{0,-9} {1,-8} {2}" -f $_.Class, $_.Side, $_.Row } | Set-Content $out
        Write-Host "  classified diff written to $out" -ForegroundColor DarkGray
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
