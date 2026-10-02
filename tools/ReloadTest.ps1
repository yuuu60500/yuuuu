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
#     .\ReloadTest.ps1 -Quiet                why a chart has had no mark lately:
#                                            its context timeline since the last
#                                            mark, and the POIs Rule 6 refused
#     .\ReloadTest.ps1 -Chain                (v2.41+) where the mark chain stops:
#                                            POI -> session -> block -> ARMED -> mark,
#                                            counted over the latest rebuild
#     .\ReloadTest.ps1 -Source "USDJPY,M5"   repaint test on that one chart
#     .\ReloadTest.ps1 -Source "USDJPY#A1B2,M5" -Versus "USDJPY#C3D4,M5"
#                                            (v2.51) fixed-window version regression:
#                                            last complete build of each source, e.g.
#                                            v2.48 and v2.51 attached side by side
#
#     -SettleHours 24   (reload check) when the two windows start at different
#                       bars, the first N hours after both warm-ups are PENDING
#                       REVIEW - reported, never passed and never explained away
#
#  Verdicts are strict: a difference inside the comparable region is a
#  MISMATCH; anything that cannot be compared is PENDING REVIEW; builds of a
#  different version or parameter digest are never compared as a repaint test.
#  (v2.50) A build is COMPLETE only when its END matches its BEGIN (build=,
#  run/init), its END counts (marks=, liqev=) equal the rows read, and every
#  row carries the build's own run/init; anything else is INCOMPLETE and is
#  listed, never compared, never a PASS. LIQ rows are judged only between two
#  builds whose liquidity history was READY; MODEL rows are judged regardless.
#  (v2.51) A build that declares ver >= 2.50, or carries run/init at all, is
#  read STRICTLY: a missing field is as bad as a wrong one - identity on
#  BEGIN, END, every tagged row inside (events AND diagnostics) and every
#  live row; END must carry build/marks/liqev/liq/unknown (+ liqwait from
#  2.51). Only a genuinely older build gets the lenient path.
#  A comparison with no common region, or with no MODEL row on either side,
#  is NOT COMPARABLE / INSUFFICIENT SAMPLE - never "0 difference".
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
      [switch]$Ctx, [switch]$Quiet, [switch]$Chain, [int]$Days = 1, [string]$LogDir = "", [int]$Warmup = 100,
      [int]$SettleHours = 24, [string]$Versus = "")

# Row layout after the tag is stripped:
#   0 symbol  1 "MODEL"  2 dir  3 cycle_id  4 block_id  5 anchor  6 model
#   7 confirm_time  8 price  9 ref_time  10 ref_level
# v2.42 liquidity rows share the layout so every check takes them as marks:
#   0 symbol  1 "LIQ"  2 side  3 0  4 0  5 level (PDH..PML/BSL/SSL)
#   6 SWEEP|BROKEN  7 resolve_time  8 level_price  9 pierce_time  10 0
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

# v2.48: every HMI line ends in ",inst=XXXX" (the indicator instance), the
# build header carries it too. MT5 only tags a line with (SYMBOL,TF), so two
# instances on the same symbol and timeframe used to share one source and
# their builds and live rows got paired with each other. Strip the trailing
# tag so every parser below sees the payload it always did, and where one
# source really has several instances, split it into "SYMBOL#XXXX,TF" - the
# symbol pattern everywhere already allows '#'. Older lines without a tag
# stay under the plain source.
$instOf = New-Object 'System.Collections.Generic.List[string]'
$idOf   = New-Object 'System.Collections.Generic.List[string]'   # v2.50 "run/init" per line; '' when not logged
$srcInst = @{}
for ($i = 0; $i -lt $all.Count; $i++) {
    $l = $all[$i]; $in = ''; $id = ''
    if ($l -match '(?:,inst=|instance=)([0-9A-Fa-f]{4})') { $in = $Matches[1].ToUpper() }
    # v2.50 identity (A-48): the terminal run id and the initialisation number.
    # Event and diagnostic rows carry ",run=R,init=I" after inst= and lose them
    # together with inst=; the BEGIN line keeps them as k=v fields of its own
    # (inst= sits mid-line there); the "starting on" line has them too.
    if ($l -match '[ ,]run=(\d+)[ ,]init=(\d+)\s*$') { $id = "$($Matches[1])/$($Matches[2])" }
    if ($l -match ',inst=[0-9A-Fa-f]{4}(?:,run=\d+,init=\d+)?\s*$') { $l = $l -replace ',inst=[0-9A-Fa-f]{4}(?:,run=\d+,init=\d+)?\s*$', ''; $all[$i] = $l }
    $instOf.Add($in); $idOf.Add($id)
    if ($in -and $l -match '\(([A-Za-z0-9._#]+,[A-Za-z0-9]+)\)') {
        if (-not $srcInst.ContainsKey($Matches[1])) { $srcInst[$Matches[1]] = @{} }
        $srcInst[$Matches[1]][$in] = $true
    }
}
$multi = @($srcInst.Keys | Where-Object { $srcInst[$_].Count -gt 1 })
if ($multi.Count -gt 0) {
    for ($i = 0; $i -lt $all.Count; $i++) {
        $in = $instOf[$i]
        if (-not $in) { continue }
        if ($all[$i] -match '\(([A-Za-z0-9._#]+),([A-Za-z0-9]+)\)' -and $multi -contains "$($Matches[1]),$($Matches[2])") {
            $all[$i] = $all[$i].Replace("($($Matches[1]),$($Matches[2]))", "($($Matches[1])#$in,$($Matches[2]))")
        }
    }
    Write-Host ("several instances on one chart source - split as SYMBOL#INSTANCE: " + ($multi -join ', ')) -ForegroundColor Yellow
}
# ---- build identity, read ONCE for every mode (v2.44 header; v2.50 A-48) ----
# A block is COMPLETE only when its END matches its BEGIN (build=, and run/init
# where logged), every row inside carries that same run/init, END marks= equals
# the MODEL rows read and END liqev= (v2.50) equals the LIQ rows read. Anything
# else - an END with another number, no END before the next BEGIN or before the
# log ends, counts that disagree - is INCOMPLETE: listed with its reasons, never
# compared, never a PASS. The old parser closed whatever build was open on any
# END, so a wrong-numbered END could still yield IDENTICAL (A-48).
$icx = [Globalization.CultureInfo]::InvariantCulture
function PT16([string]$v) {
    $d = [datetime]::MinValue
    if ($v) { [void][datetime]::TryParseExact($v.Trim(), 'yyyy.MM.dd HH:mm', $icx, [Globalization.DateTimeStyles]::None, [ref]$d) }
    return $d
}
function RowTime([string]$r) {
    $t = [datetime]::MinValue
    $c = $r -split ','
    if ($c.Count -gt 7) { [void][datetime]::TryParseExact($c[7], 'yyyy.MM.dd HH:mm:ss', $icx, [Globalization.DateTimeStyles]::None, [ref]$t) }
    return $t
}
function RowKind([string]$r) { $c = $r -split ','; if ($c.Count -gt 1) { return $c[1] } return '?' }
function KV([string]$s) { $m = @{}; foreach ($p in ($s -split ',')) { $kv = $p -split '=', 2; if ($kv.Count -eq 2) { $m[$kv[0].Trim()] = $kv[1].Trim() } }; return $m }

function VerNum([string]$v) { $d = [decimal]0; if ([decimal]::TryParse($v, [Globalization.NumberStyles]::Float, $icx, [ref]$d)) { return $d } return [decimal]0 }

function New-Block($src, $head, $idx, $id) {
    $m = KV $head
    $v = '?'; if ($m.ContainsKey('ver')) { $v = $m['ver'] } elseif ($verNow.ContainsKey($src)) { $v = $verNow[$src] }
    # A-51: strict whenever the build says it is new enough to know better, or
    # shows it knows identity at all - a damaged v2.50 build must not fall
    # back to the lenient path written for v2.48 logs.
    $vn = VerNum $v
    $strict = ($vn -ge [decimal]2.50) -or [bool]$id
    $we = [datetime]::MinValue; $west = $false; $ws = ''
    if ($m.ContainsKey('warmup_end')) { $we = PT16 $m['warmup_end']; $ws = $m['warmup_end'] }
    else { $we = (PT16 $m['from']).AddMinutes(5 * $Warmup); $west = $true }     # pre-v2.44: estimate, flagged
    [pscustomobject]@{ Src = $src; Head = $head; Rows = (New-Object System.Collections.ArrayList); Lines = (New-Object System.Collections.ArrayList); Tail = ''
                       Ver = $v; Params = $(if ($m.ContainsKey('params')) { $m['params'] } else { '?' })
                       Inst = $(if ($m.ContainsKey('inst')) { $m['inst'].ToUpper() } else { '?' })
                       Id = $id; Build = $(if ($m.ContainsKey('build')) { $m['build'] } else { '?' })
                       From = (PT16 $m['from']); To = (PT16 $m['to']); FromS = $m['from']; ToS = $m['to']
                       WarmEnd = $we; WarmEst = $west; WarmS = $ws; BeginIdx = $idx; EndIdx = -1
                       Liq = '?'; LiqEv = -1; Marks = -1; Unknown = -1; LiqWait = -1; ModelN = 0; LiqN = 0
                       Status = 'OPEN'; Why = (New-Object System.Collections.ArrayList); BadRows = 0
                       Strict = $strict; V251 = ($vn -ge [decimal]2.51); NoIdRows = 0; BadKinds = @{} }
}
function Note-Row($bk, [string]$msg, [string]$id) {
    # every TAGGED line inside a strict build carries the build's own identity
    if (-not $bk.Strict) { return }
    $kind = $(if ($msg -match '^(HMI-[A-Z-]+)') { $Matches[1] } else { 'HMI-?' })
    if (-not $id)               { $bk.NoIdRows++; $bk.BadKinds[$kind] = 1 }
    elseif ($id -ne $bk.Id)     { $bk.BadRows++;  $bk.BadKinds[$kind] = 1 }
}
function Close-Block($bk) {
    if ($bk.Strict -and -not $bk.Id) { [void]$bk.Why.Add("BEGIN without run/init (v$($bk.Ver) log must carry it)") }
    $kinds = ($bk.BadKinds.Keys | Sort-Object) -join '/'
    if ($bk.NoIdRows -gt 0) { [void]$bk.Why.Add("$($bk.NoIdRows) row(s) without run/init ($kinds)") }
    if ($bk.BadRows  -gt 0) { [void]$bk.Why.Add("$($bk.BadRows) row(s) carry another run/init than the BEGIN ($kinds)") }
    $bk.Status = $(if ($bk.Why.Count -eq 0) { 'COMPLETE' } else { 'INCOMPLETE' })
}

$blocks = @(); $open = @{}; $verNow = @{}; $liveAll = @(); $orphanRows = 0; $orphanEnds = 0
for ($i = 0; $i -lt $all.Count; $i++) {
    $l = $all[$i]
    if ($l -notmatch 'HMI') { continue }
    $src = if ($l -match '\(([A-Za-z0-9._#]+,[A-Za-z0-9]+)\)') { $Matches[1] } else { '?' }
    $msg = if ($l -match '\(([A-Za-z0-9._#]+,[A-Za-z0-9]+)\)\s+(HMI.*)$') { $Matches[2] } else { '' }
    $id  = $idOf[$i]
    if ($l -match 'HMI v(\S+) starting on') { $verNow[$src] = $Matches[1]; continue }
    if ($l -match 'HMI-BUILD-BEGIN,(.*)$') {
        if ($open.ContainsKey($src)) {                                   # the previous build never ended
            $prev = $open[$src]; [void]$prev.Why.Add("no END before the next BEGIN (build $($prev.Build))"); Close-Block $prev; $blocks += $prev
        }
        $open[$src] = New-Block $src $Matches[1] $i $id
        continue
    }
    if ($l -match 'HMI-BUILD-END,(.*)$') {
        if (-not $open.ContainsKey($src)) { $orphanEnds++; continue }    # END with no BEGIN: nothing to close
        $bk = $open[$src]; $bk.Tail = $Matches[1]; $bk.EndIdx = $i
        $e  = KV $Matches[1]
        $eb = $(if ($e.ContainsKey('build')) { $e['build'] } else { '?' })
        if ($eb -ne $bk.Build) { [void]$bk.Why.Add("END build=$eb, BEGIN build=$($bk.Build)") }
        if ($bk.Strict) {
            if (-not $id)                      { [void]$bk.Why.Add('END without run/init') }
            elseif ($bk.Id -and $id -ne $bk.Id) { [void]$bk.Why.Add("END run/init $id, BEGIN $($bk.Id)") }
        }
        $isInt = { param($k) $e.ContainsKey($k) -and ($e[$k] -match '^\d+$') }
        if (& $isInt 'marks') { $bk.Marks = [int]$e['marks']; if ($bk.Marks -ne $bk.ModelN) { [void]$bk.Why.Add("END marks=$($bk.Marks) but $($bk.ModelN) MODEL row(s) in the block") } }
        else { [void]$bk.Why.Add('END without a valid marks=') }
        if (& $isInt 'liqev') { $bk.LiqEv = [int]$e['liqev']; if ($bk.LiqEv -ne $bk.LiqN) { [void]$bk.Why.Add("END liqev=$($bk.LiqEv) but $($bk.LiqN) LIQ row(s) in the block") } }
        elseif ($bk.Strict) { [void]$bk.Why.Add('END without a valid liqev=') }
        if ($e.ContainsKey('liq') -and ($e['liq'] -eq 'READY' -or $e['liq'] -eq 'WAITING')) { $bk.Liq = $e['liq'] }
        elseif ($bk.Strict) { [void]$bk.Why.Add("END without a valid liq= (READY|WAITING)") }
        if (& $isInt 'unknown') { $bk.Unknown = [int]$e['unknown'] }
        elseif ($bk.Strict) { [void]$bk.Why.Add('END without a valid unknown=') }
        if ($bk.V251) {
            if (& $isInt 'liqwait') {
                $bk.LiqWait = [int]$e['liqwait']
                if (($bk.Liq -eq 'WAITING') -ne ($bk.LiqWait -gt 0)) { [void]$bk.Why.Add("END liq=$($bk.Liq) but liqwait=$($bk.LiqWait)") }
            } else { [void]$bk.Why.Add('END without a valid liqwait= (v2.51+)') }
        }
        Close-Block $bk; $blocks += $bk; $open.Remove($src)
        continue
    }
    if ($msg -and $open.ContainsKey($src)) {
        # every tagged line of the build - events and the diagnostics -Chain
        # counts - is checked BEFORE it is kept (A-51). The untagged "HMI: ..."
        # notices are OnInit messages and carry no identity by design.
        if ($msg -match '^HMI-') { Note-Row $open[$src] $msg $id }
        if ($msg -match '^HMI-LIVE,') { [void]$open[$src].Why.Add('HMI-LIVE row inside a historical build') }
        [void]$open[$src].Lines.Add($msg)
    }
    if ($l -match 'HMI-BUILD,(.*)$') {
        if (-not $open.ContainsKey($src)) { $orphanRows++; continue }
        $bk = $open[$src]
        [void]$bk.Rows.Add($Matches[1])
        $k = RowKind $Matches[1]; if ($k -eq 'MODEL') { $bk.ModelN++ } elseif ($k -eq 'LIQ') { $bk.LiqN++ }
        continue
    }
    if ($l -match 'HMI-LIVE,(.*)$') { $liveAll += [pscustomobject]@{ Src = $src; Idx = $i; Row = $Matches[1]; Id = $id } }
}
foreach ($src in @($open.Keys)) { $bk = $open[$src]; [void]$bk.Why.Add("no END (the log ends inside build $($bk.Build))"); Close-Block $bk; $blocks += $bk }
$blocks = @($blocks | Sort-Object BeginIdx)

# -Live is the check you run while waiting for samples: it needs no build
# block and no -Source, and it discovers the charts from the log itself, so
# adding symbols does not mean editing a list.
if ($Live) {
    # A chart with no live rows is either quiet or not running, and the count
    # alone cannot tell which. Two more columns can: the newest mark ANY build
    # of that chart has produced (if a rebuild today also stops days ago, live
    # and build agree the chart has been quiet), and the context state after
    # the last H4 event (RANGE / TRANSITION mint no setups, Rule 2 / BRI-07).
    $tally = @{}; $newest = @{}; $ctxNow = @{}
    foreach ($l in $all) {
        if ($l -match 'HMI-CTX,') {
            $src = if ($l -match '\(([A-Za-z0-9._#]+,[A-Za-z0-9]+)\)') { $Matches[1] } else { '?' }
            if ($l -match 'ctx=([A-Z_]+)') { $c = $Matches[1] } else { $c = '?' }
            # The event bar is when the state was last TOUCHED, not when it
            # began - a BOS keeps BULLISH bullish - so print it as such.
            $kd = if ($l -match 'HMI-CTX,[^,]*,([A-Z_]+),') { $Matches[1] } else { '?' }
            if ($l -match ',bar=([0-9.: ]+),') { $c = "$c   (last: $kd $($Matches[1].Trim()))" }
            $ctxNow[$src] = $c
            continue
        }
        if ($l -notmatch 'HMI-(LIVE|BUILD),(.*)$') { continue }
        $cols = $Matches[2] -split ','
        $src = if ($l -match '\(([A-Za-z0-9._#]+,[A-Za-z0-9]+)\)') { $Matches[1] } else { '?' }
        if (-not $tally.ContainsKey($src)) { $tally[$src] = 0 }
        if ($l -match 'HMI-LIVE,') { $tally[$src]++ }
        # 'yyyy.MM.dd HH:mm:ss' sorts correctly as text - no culture parsing.
        # newest MODEL mark only: a v2.42 LIQ sweep row is not a link of the mark chain
        if ($cols.Count -gt 7 -and $cols[1] -eq 'MODEL' -and ((-not $newest.ContainsKey($src)) -or $cols[7] -gt $newest[$src])) { $newest[$src] = $cols[7] }
    }
    if ($tally.Count -eq 0) {
        Write-Host "`nno HMI rows at all. Is InpLogSignals = true ?" -ForegroundColor Red
        exit
    }
    Write-Host "`nLIVE marks so far:`n" -ForegroundColor Cyan
    Write-Host ("  {0,-14} {1,5}   {2,-20} {3}" -f 'chart', 'live', 'newest mark', 'context after last H4 event') -ForegroundColor DarkGray
    $total = 0
    foreach ($k in ($tally.Keys | Sort-Object)) {
        $n = $tally[$k]; $total += $n
        $nm = if ($newest.ContainsKey($k)) { $newest[$k] } else { '-' }
        $cx = if ($ctxNow.ContainsKey($k)) { $ctxNow[$k] } else { '-' }
        Write-Host ("  {0,-14} {1,5}   {2,-20} {3}" -f $k, $n, $nm, $cx) -ForegroundColor $(if ($n -gt 0) { 'Green' } else { 'Gray' })
    }
    Write-Host ("`n  total {0}" -f $total)
    if ($total -eq 0) {
        Write-Host "`nnothing yet. Leave the charts running and do NOT reload them." -ForegroundColor Yellow
    } else {
        Write-Host "`nnow reload ONLY the charts with live rows (Ctrl+I -> HMI -> Properties -> OK)," -ForegroundColor Yellow
        Write-Host "wait a minute for the log to flush," -ForegroundColor Yellow
        Write-Host "then run:  .\ReloadTest.ps1 -LiveVsBuild -Days $Days" -ForegroundColor Yellow
    }
    exit
}

# -Chain (v2.41+): the diagnostic lines HMI-POI / HMI-SESS / HMI-BLK / HMI-ARM
# trace every link between a trend and a mark. Only the latest COMPLETE
# rebuild of each chart is read: it covers the whole window in one pass, and
# sequence ids differ between rebuilds (A-20), so mixing builds would count
# the same POI twice.
if ($Chain) {
    # the latest COMPLETE rebuild of each chart. An INCOMPLETE block (A-48) is
    # never read: a cut or mis-ended build would under-count every link.
    $last = @{}; $skipped = @{}
    foreach ($bk in $blocks) {
        if ($bk.Status -ne 'COMPLETE') { $skipped[$bk.Src] = 1 + $(if ($skipped.ContainsKey($bk.Src)) { $skipped[$bk.Src] } else { 0 }); continue }
        $last[$bk.Src] = [pscustomobject]@{ From = $bk.FromS; To = $bk.ToS; Warm = $bk.WarmS; Lines = $bk.Lines }
    }
    foreach ($s in ($skipped.Keys | Sort-Object)) { Write-Host "  $s : $($skipped[$s]) INCOMPLETE build(s) skipped" -ForegroundColor Yellow }
    if ($last.Count -eq 0) { Write-Host "`nno complete rebuild found." -ForegroundColor Red; exit }
    $any = $false
    $chainSrc = @($last.Keys | Sort-Object)
    if ($Source -ne "") {
        # one chart per run keeps each result to one screen - long output
        # only ends up in stitched screenshots that mix charts up
        if ($last.Keys -notcontains $Source) { Write-Host "`n'$Source' has no complete rebuild. Charts: $($chainSrc -join ', ')" -ForegroundColor Red; exit }
        $chainSrc = @($Source)
    }
    foreach ($src in $chainSrc) {
        $L = $last[$src].Lines
        $diag = @($L | Where-Object { $_ -match '^HMI-(POI|SESS|BLK|ARM),' })
        Write-Host "`n--- $src   rebuild to=$($last[$src].To)" -ForegroundColor Cyan
        if ($diag.Count -eq 0) { Write-Host "  no chain diagnostic lines in this rebuild (chart still on a version before v2.41?)" -ForegroundColor Yellow; continue }
        $any = $true
        $marks = @($L | Where-Object { $_ -match '^HMI-BUILD,[^,]*,MODEL,' } | ForEach-Object { ($_ -split ',')[8] })
        $liq   = @($L | Where-Object { $_ -match '^HMI-BUILD,[^,]*,LIQ,' })
        # The H4 feed reaches ~80 days back, the M5 feed ~26. Everything H4
        # did before the first M5 bar (plus the M5 warm-up, where Phase 3 does
        # not run) happened with no M5 bar that could touch anything, so it is
        # counted separately instead of passing for evidence.
        $ic2 = [Globalization.CultureInfo]::InvariantCulture
        $m5Start = [datetime]::ParseExact($last[$src].From, 'yyyy.MM.dd HH:mm', $ic2).AddMinutes(5 * $Warmup)
        if ($last[$src].Warm) { $m5Start = [datetime]::ParseExact($last[$src].Warm, 'yyyy.MM.dd HH:mm', $ic2) }   # v2.44+: logged, not estimated
        $ws = $m5Start.ToString('yyyy.MM.dd HH:mm', $ic2)
        $nm = if ($marks.Count) { @($marks | Sort-Object)[-1].Substring(0, 16) } else { $ws }
        if ($nm -lt $ws) { $nm = $ws }
        $nmLabel = if ($marks.Count) { "since $nm" } else { 'since M5 start' }
        Write-Host ("  M5 window after warm-up starts ~{0}; H4-only history before it is excluded" -f $ws) -ForegroundColor DarkGray
        function Bar([string]$m) { if ($m -match 'bar=([0-9.: ]+)') { $Matches[1].Trim() } else { '' } }
        $steps = [ordered]@{
            'POI created'              = '^HMI-POI,[^,]*,NEW,'
            'POI touched -> session'   = '^HMI-SESS,[^,]*,START,'
            'M5 block (trend dir)'     = '^HMI-BLK,.*,counter=0,'
            'block ARMED'              = '^HMI-ARM,'
        }
        Write-Host ("  {0,-26} {1,8} {2,14}" -f 'step', 'M5 window', $nmLabel) -ForegroundColor DarkGray
        $stop = ''
        foreach ($k in $steps.Keys) {
            $all1 = @($diag | Where-Object { $_ -match $steps[$k] -and (Bar $_) -ge $ws })
            $aft  = @($all1 | Where-Object { (Bar $_) -gt $nm })
            Write-Host ("  {0,-26} {1,8} {2,14}" -f $k, $all1.Count, $aft.Count)
            if (-not $stop -and $aft.Count -eq 0) { $stop = $k }
        }
        Write-Host ("  {0,-26} {1,8} {2,14}" -f 'mark', $marks.Count, 0)
        if ($liq.Count) {
            $lk = $liq | ForEach-Object { $c = $_ -split ','; "$($c[6]) $($c[7])" } | Group-Object | Sort-Object Name | ForEach-Object { "$($_.Name) x$($_.Count)" }
            Write-Host "  liquidity (not a chain link): $($lk -join ', ')" -ForegroundColor DarkGray
        }
        # what ended the POIs and sessions since the last mark
        $out = @($diag | Where-Object { $_ -match '^HMI-POI,[^,]*,(INVALID|EXPIRED|OUT),' -and (Bar $_) -gt $nm } |
                 ForEach-Object { if ($_ -match '^HMI-POI,[^,]*,([A-Z]+),.*was=([A-Z]+)') { "$($Matches[1]) (was $($Matches[2]))" } })
        if ($out.Count) { Write-Host "  POIs lost since the mark : $((($out | Group-Object | ForEach-Object { "$($_.Name) x$($_.Count)" }) -join ', '))" }
        $ends = @($diag | Where-Object { $_ -match '^HMI-SESS,[^,]*,END,' -and (Bar $_) -gt $nm } |
                  ForEach-Object { if ($_ -match 'reason=([A-Z_]+)') { $Matches[1] } })
        if ($ends.Count) { Write-Host "  sessions ended since     : $((($ends | Group-Object | ForEach-Object { "$($_.Name) x$($_.Count)" }) -join ', '))" }
        # POI fate over the whole window. A POI can only be INVALIDATED by an
        # H4 close beyond its far edge, so price crossed it; if the context
        # agreed with the POI for its whole life, some M5 bar should have
        # touched it and opened a session. One that was never touched in that
        # case is the evidence A-37 is looking for. Where the context left the
        # POI's direction first, BRI-07(a) explains the missing touch.
        $ctxEv = @($L | Where-Object { $_ -match '^HMI-CTX,' } | ForEach-Object {
                     if ($_ -match 'ctx=([A-Z_]+).*,bar=([0-9.: ]+),') { [pscustomobject]@{ Bar = $Matches[2].Trim(); Ctx = $Matches[1] } } })
        $touched = @{}
        foreach ($x in $diag) { if ($x -match '^HMI-SESS,[^,]*,START,.*poi=(\d+)') { $touched[$Matches[1]] = $true } }
        $pois = [ordered]@{}
        foreach ($x in $diag) {
            if ($x -match '^HMI-POI,[^,]*,NEW,id=(\d+),dir=(-?\d+),.*bar=([0-9.: ]+)$') {
                $pois[$Matches[1]] = [pscustomobject]@{ Id = $Matches[1]; Dir = [int]$Matches[2]; Born = $Matches[3].Trim(); End = ''; How = '' }
            } elseif ($x -match '^HMI-POI,[^,]*,(INVALID|EXPIRED|OUT),id=(\d+),.*bar=([0-9.: ]+)$') {
                if ($pois.Contains($Matches[2]) -and -not $pois[$Matches[2]].End) { $pois[$Matches[2]].End = $Matches[3].Trim(); $pois[$Matches[2]].How = $Matches[1] }
            }
        }
        $fate = [ordered]@{ 'touched (session)' = 0; 'untouched, context left first' = 0; 'untouched, INVALID, context agreed' = 0; 'untouched, expired / out' = 0; 'still active' = 0 }
        $sus = @(); $pre = 0
        foreach ($p in $pois.Values) {
            # gone before any M5 bar could touch it: not evidence either way.
            # An INVALID needs its whole breaking H4 bar inside the M5 window.
            $lim = $ws
            if ($p.How -eq 'INVALID') { $lim = ([datetime]::ParseExact($ws, 'yyyy.MM.dd HH:mm', $ic2)).AddHours(4).ToString('yyyy.MM.dd HH:mm', $ic2) }
            if ($p.End -and $p.End -le $lim) { $pre++; continue }
            if ($touched.ContainsKey($p.Id)) { $fate['touched (session)']++; continue }
            if (-not $p.End)                 { $fate['still active']++; continue }
            if ($p.How -ne 'INVALID')        { $fate['untouched, expired / out']++; continue }
            $want = if ($p.Dir -gt 0) { 'BULLISH' } else { 'BEARISH' }
            $left = @($ctxEv | Where-Object { $_.Bar -gt $p.Born -and $_.Bar -lt $p.End -and $_.Ctx -ne $want }).Count
            if ($left -gt 0) { $fate['untouched, context left first']++ }
            else { $fate['untouched, INVALID, context agreed']++; $sus += $p }
        }
        Write-Host "  POI fate (POIs alive inside the M5 window):" -ForegroundColor DarkGray
        foreach ($k in $fate.Keys) {
            Write-Host ("      {0,-36} {1,4}" -f $k, $fate[$k]) -ForegroundColor $(if ($k -like '*agreed*' -and $fate[$k] -gt 0) { 'Red' } else { 'Gray' })
        }
        Write-Host ("      {0,-36} {1,4}" -f '(ended in H4-only history, excluded)', $pre) -ForegroundColor DarkGray
        foreach ($p in ($sus | Select-Object -First 5)) {
            Write-Host ("        id={0} dir={1} created {2} -> INVALID {3}" -f $p.Id, $p.Dir, $p.Born, $p.End) -ForegroundColor Red
        }
        if ($stop) { Write-Host "  since the last mark the chain stops at: $stop" -ForegroundColor Yellow }
        else       { Write-Host "  every link fired since the last mark; the model step produced nothing" -ForegroundColor Yellow }
    }
    if (-not $any) { Write-Host "`nreload the charts on v2.41 or later first, then run this again." -ForegroundColor Yellow }
    exit
}

# -Quiet: a chart with no recent mark is either quiet by rule or stalled, and
# the current context alone cannot tell (a trend that began an hour ago says
# nothing about the ten days before). A mark needs, in order: a trending
# context, an ACTIVE H4 POI in that direction, price reaching it, an M5
# block, ARMED, a model. Only the first link and the POI refusals are in the
# log, so this reports exactly those two, from the last mark to now.
if ($Quiet) {
    $ic = [Globalization.CultureInfo]::InvariantCulture
    function P16([string]$t) { $d = [datetime]::MinValue
        [void][datetime]::TryParseExact($t.Trim().Substring(0, [Math]::Min(16, $t.Trim().Length)), 'yyyy.MM.dd HH:mm', $ic, [Globalization.DateTimeStyles]::None, [ref]$d); $d }
    $ev = @{}; $newest = @{}; $lastTo = @{}; $rej = @{}
    foreach ($l in $all) {
        if ($l -notmatch '\(([A-Za-z0-9._#]+,[A-Za-z0-9]+)\)') { continue }
        $src = $Matches[1]
        if ($l -match 'HMI-CTX,[^,]*,([A-Z_]+),.*ctx=([A-Z_]+),str=(\d+).*,bar=([0-9.: ]+),') {
            if (-not $ev.ContainsKey($src)) { $ev[$src] = @{} }
            $k = "$($Matches[4].Trim())|$($Matches[1])|$($Matches[2])"
            $ev[$src][$k] = [pscustomobject]@{ Bar = $Matches[4].Trim(); Kind = $Matches[1]; Ctx = $Matches[2]; Str = $Matches[3] }
        } elseif ($l -match 'HMI-REJECT,[^,]*,H4POI,(BULL|BEAR),fvg=([0-9.: ]+),') {
            if (-not $rej.ContainsKey($src)) { $rej[$src] = @{} }
            $rej[$src]["$($Matches[1])|$($Matches[2].Trim())"] = $Matches[2].Trim()
        } elseif ($l -match 'HMI-BUILD-BEGIN,.*,to=([0-9.: ]+)') {
            $t = $Matches[1].Trim(); if (-not $lastTo.ContainsKey($src) -or $t -gt $lastTo[$src]) { $lastTo[$src] = $t }
        } elseif ($l -match 'HMI-(LIVE|BUILD),(.*)$') {
            $c = $Matches[2] -split ','
            if ($c.Count -gt 7 -and $c[1] -eq 'MODEL' -and ((-not $newest.ContainsKey($src)) -or $c[7] -gt $newest[$src])) { $newest[$src] = $c[7] }
        }
    }
    foreach ($src in ($ev.Keys | Sort-Object)) {
        $nm  = if ($newest.ContainsKey($src)) { $newest[$src] } else { '' }
        Write-Host "`n--- $src   newest mark: $(if ($nm) { $nm } else { 'none' })" -ForegroundColor Cyan
        if (-not $nm) { continue }
        $t0  = P16 $nm
        $now = if ($lastTo.ContainsKey($src)) { (P16 $lastTo[$src]).AddMinutes(5) } else { $t0 }
        $seq = @($ev[$src].Values | Sort-Object Bar)
        $before = @($seq | Where-Object { (P16 $_.Bar) -le $t0 })
        $after  = @($seq | Where-Object { (P16 $_.Bar) -gt $t0 })
        $state = if ($before.Count) { $before[-1].Ctx } else { '?' }
        # time in each state from the last mark to the end of the newest build
        $hrs = @{}; $cur = $state; $from = $t0
        foreach ($e in $after) { $t = P16 $e.Bar; $hrs[$cur] += ($t - $from).TotalHours; $cur = $e.Ctx; $from = $t }
        $hrs[$cur] += ($now - $from).TotalHours
        $tot = 0.0; foreach ($v in $hrs.Values) { $tot += $v }
        $trend = 0.0; foreach ($k2 in 'BULLISH', 'BEARISH') { if ($hrs.ContainsKey($k2)) { $trend += $hrs[$k2] } }
        Write-Host ("  context at that mark : {0}" -f $state)
        Write-Host ("  since then (to {0:yyyy.MM.dd HH:mm}): {1:N0} calendar h (weekends included), trending {2:N0} h ({3:P0})" -f $now, $tot, $trend, $(if ($tot -gt 0) { $trend / $tot } else { 0 }))
        foreach ($k2 in ($hrs.Keys | Sort-Object)) { Write-Host ("      {0,-11} {1,6:N0} h" -f $k2, $hrs[$k2]) -ForegroundColor DarkGray }
        $show = @($after | Select-Object -Last 12)
        if ($after.Count -gt $show.Count) { Write-Host "  ... $($after.Count - $show.Count) earlier event(s) not shown" -ForegroundColor DarkGray }
        foreach ($e in $show) { Write-Host ("    {0}  {1,-13} -> {2,-10} str={3}" -f $e.Bar, $e.Kind, $e.Ctx, $e.Str) }
        $nr = 0; if ($rej.ContainsKey($src)) { $nr = @($rej[$src].Values | Where-Object { (P16 $_) -gt $t0 }).Count }
        Write-Host ("  H4 FVGs whose POI Rule 6 refused since the mark: {0}" -f $nr)
    }
    Write-Host "`nwhat this cannot show: whether an ACTIVE POI in the trend's direction existed" -ForegroundColor DarkGray
    Write-Host "and whether price reached it - touches and sessions are not logged." -ForegroundColor DarkGray
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

if ($blocks.Count -eq 0) {
    Write-Host "`nno HMI-BUILD lines found." -ForegroundColor Red
    Write-Host "set InpLogSignals = true on the chart you want to test." -ForegroundColor Yellow
    exit
}

function BlockLabel($b) {
    $w = $b.WarmEnd.ToString('yyyy.MM.dd HH:mm'); if ($b.WarmEst) { $w = "~$w (estimated)" }
    $idt = $(if ($b.Id) { " id=$($b.Id)" } else { '' })
    $lq  = $(if ($b.Liq -ne '?') { " liq=$($b.Liq)" } else { '' })
    $s = "v{0} params={1} build={2}{3}{4} from={5} to={6} warmup_end={7} rows={8} MODEL + {9} LIQ" -f $b.Ver, $b.Params, $b.Build, $idt, $lq,
            $b.From.ToString('yyyy.MM.dd HH:mm'), $b.To.ToString('yyyy.MM.dd HH:mm'), $w, $b.ModelN, $b.LiqN
    if ($b.Status -ne 'COMPLETE') { $s += "  [INCOMPLETE: " + ($b.Why -join '; ') + "]" }
    return $s
}

$sources = @($blocks | Group-Object Src)     # @(): one group is otherwise a GroupInfo whose .Count is its row count
Write-Host "`nsources found: $($sources.Count)`n" -ForegroundColor Cyan
if ($orphanRows -gt 0) { Write-Host "  $orphanRows HMI-BUILD row(s) outside any build - ignored" -ForegroundColor Yellow }
if ($orphanEnds -gt 0) { Write-Host "  $orphanEnds HMI-BUILD-END line(s) with no open BEGIN - ignored" -ForegroundColor Yellow }
# Every block of every chart runs to a hundred lines after a few days, which
# only ends up in scrolling screenshots. List blocks in full only where they
# are the point: the plain listing, or the one chart named with -Source.
$fullList = (-not $LiveVsBuild -and -not $Rejects -and $Source -eq "")
foreach ($g in $sources) {
    if ($fullList -or $g.Name -eq $Source) {
        Write-Host ("  {0}  -> {1} block(s)" -f $g.Name, $g.Count) -ForegroundColor White
        $i = 0
        foreach ($bk in $g.Group) { Write-Host ("      [{0}] {1}" -f $i, (BlockLabel $bk)) -ForegroundColor $(if ($bk.Status -eq 'COMPLETE') { 'Gray' } else { 'Red' }); $i++ }
    } else {
        $inc = @($g.Group | Where-Object { $_.Status -ne 'COMPLETE' }).Count
        Write-Host ("  {0,-14} {1,3} block(s), last rows={2}{3}" -f $g.Name, $g.Count, $g.Group[-1].Rows.Count, $(if ($inc) { "  ($inc INCOMPLETE)" } else { '' })) -ForegroundColor $(if ($inc) { 'Yellow' } else { 'DarkGray' })
    }
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

# Multiset difference with the init-relative ids (A-20) set aside: a key
# that occurs twice on one side and once on the other is still a difference.
function DiffRows($ra, $rb) {
    $ca = @{}; $sa = @{}; $cb = @{}; $sb = @{}
    foreach ($r in $ra) { $k = Key $r; if ($ca.ContainsKey($k)) { $ca[$k]++ } else { $ca[$k] = 1; $sa[$k] = $r } }
    foreach ($r in $rb) { $k = Key $r; if ($cb.ContainsKey($k)) { $cb[$k]++ } else { $cb[$k] = 1; $sb[$k] = $r } }
    $out = @()
    foreach ($k in $ca.Keys) { $n = $ca[$k]; if ($cb.ContainsKey($k)) { $n -= $cb[$k] }
        for ($j = 0; $j -lt $n; $j++) { $out += [pscustomobject]@{ Side = 'A only'; Row = $sa[$k]; Time = (RowTime $sa[$k]) } } }
    foreach ($k in $cb.Keys) { $n = $cb[$k]; if ($ca.ContainsKey($k)) { $n -= $ca[$k] }
        for ($j = 0; $j -lt $n; $j++) { $out += [pscustomobject]@{ Side = 'B only'; Row = $sb[$k]; Time = (RowTime $sb[$k]) } } }
    return @($out | Sort-Object Time)
}
function RowLabel([string]$r) { $c = $r -split ','; if ($c[1] -eq 'LIQ') { return "LIQ $($c[5]) $($c[6])" } return $c[6] }

function Show-LiveVsBuild([string]$src) {
    # Every pair of consecutive complete builds of this chart brackets a live
    # stretch: A ended, the chart ran live, B rebuilt everything. Over the
    # bars that stretch provably covered - after A's last bar, before B's
    # last bar - live and rebuild must agree IN BOTH DIRECTIONS:
    #   live only   the rebuild lost an event the live run produced
    #   build only  the rebuild has an event the live run never produced
    # Either one is a failure. A pair whose version or parameter digest
    # differs, or is not logged, is PENDING REVIEW, never a pass. So is a
    # pair with an INCOMPLETE build (A-48). A live row from another run/init
    # than build A is not A's lifetime and is set aside. LIQ rows are judged
    # only when both builds report liquidity READY (A-47): a build still
    # WAITING for history had nothing to sweep, so MODEL rows are judged and
    # LIQ rows are PENDING - neither a liquidity pass nor a MODEL failure.
    Write-Host "`n--- $src : LIVE vs BUILD ---" -ForegroundColor Cyan
    $sel = @($blocks | Where-Object { $_.Src -eq $src })
    $lv  = @($liveAll | Where-Object { $_.Src -eq $src })
    if ($sel.Count -lt 2) { Write-Host "  fewer than two builds - nothing brackets a live stretch yet." -ForegroundColor Yellow; return }
    $pairs = 0; $cmp = 0; $pend = 0; $liveN = 0; $bad = @(); $okRows = @(); $pendWhy = @(); $liqPend = 0
    for ($k = 1; $k -lt $sel.Count; $k++) {
        $A = $sel[$k - 1]; $B = $sel[$k]
        $rows = @($lv | Where-Object { $_.Idx -gt $A.EndIdx -and $_.Idx -lt $B.BeginIdx })
        $cs = $A.To.AddMinutes(10); $ce = $B.To
        if ($B.WarmEnd.AddMinutes(5) -gt $cs) { $cs = $B.WarmEnd.AddMinutes(5) }
        $bIn = @($B.Rows | Where-Object { $t = RowTime $_; $t -ge $cs -and $t -le $ce })
        if ($rows.Count -eq 0 -and $bIn.Count -eq 0) { continue }
        $pairs++
        $why = ''
        if ($A.Status -ne 'COMPLETE' -or $B.Status -ne 'COMPLETE') { $why = 'INCOMPLETE build: ' + ((@($A.Why) + @($B.Why)) -join '; ') }
        elseif ($A.Ver -ne $B.Ver)                       { $why = "version $($A.Ver) -> $($B.Ver)" }
        elseif ($A.Params -eq '?' -or $B.Params -eq '?') { $why = 'parameter digest not logged (pre-v2.44)' }
        elseif ($A.Params -ne $B.Params)                 { $why = "parameters changed ($($A.Params) -> $($B.Params))" }
        if ($ce -lt $cs)                                 { $why = 'no fully covered bar between the two builds' }
        if ($why) { $pend++; $pendWhy += "build $($A.Build)->$($B.Build): $why ($($rows.Count) live row(s))"; continue }
        # A-51: live rows obey the build's identity rule. In a strict pair a
        # live row with no run/init, or another one than build A's (the
        # lifetime that produced them), makes the pair PENDING - not a row
        # quietly set aside while the rest still passes.
        if ($A.Strict) {
            $noId  = @($rows | Where-Object { -not $_.Id }).Count
            $alien = @($rows | Where-Object { $_.Id -and $_.Id -ne $A.Id }).Count
            if ($noId -or $alien) {
                $pend++
                $pendWhy += "build $($A.Build)->$($B.Build): live rows without run/init $noId, from another run/init than build $($A.Build) $alien"
                continue
            }
        }
        $cmp++
        $liqCmp = ($A.Liq -ne 'WAITING' -and $B.Liq -ne 'WAITING')
        if (-not $liqCmp) {
            $liqPend++
            $pendWhy += "build $($A.Build)->$($B.Build): liquidity WAITING for history in build $(if ($A.Liq -eq 'WAITING') { $A.Build } else { $B.Build }) - LIQ rows pending, MODEL rows compared"
            $bIn = @($bIn | Where-Object { (RowKind $_) -eq 'MODEL' })
        }
        $lIn  = @($rows | Where-Object { $t = RowTime $_.Row; $t -ge $cs -and $t -le $ce } | ForEach-Object { $_.Row })
        $lOut = $rows.Count - $lIn.Count
        if ($lOut -gt 0) { $pendWhy += "build $($A.Build)->$($B.Build): $lOut live row(s) on an edge bar, not provably covered" }
        if (-not $liqCmp) { $lIn = @($lIn | Where-Object { (RowKind $_) -eq 'MODEL' }) }
        $liveN += $lIn.Count
        $okRows += $lIn
        foreach ($d in (DiffRows $lIn $bIn)) {
            $side = 'build only'; if ($d.Side -eq 'A only') { $side = 'live only' }
            $bad += [pscustomobject]@{ Side = $side; Row = $d.Row; Pair = "$($A.Build)->$($B.Build)" }
        }
    }
    Write-Host ("  build pairs with a live stretch: {0}   comparable: {1}   pending review: {2}   liquidity pending: {3}" -f $pairs, $cmp, $pend, $liqPend)
    foreach ($w in $pendWhy) { Write-Host "    pending: $w" -ForegroundColor Yellow }
    if ($cmp -eq 0) { Write-Host "  nothing comparable yet - no PASS can be given." -ForegroundColor Yellow; return }
    Write-Host ("  live events compared: {0}" -f $liveN)
    if ($okRows.Count) {
        $bm = $okRows | Group-Object { RowLabel $_ } | Sort-Object Name | ForEach-Object { "$($_.Name) $($_.Count)" }
        Write-Host ("  by model: " + ($bm -join '  |  '))
    }
    if ($bad.Count -eq 0) {
        $what = $(if ($liqPend -eq 0) { 'MODEL + LIQ' } else { "MODEL only; LIQ pending in $liqPend pair(s)" })
        Write-Host "  AGREE BOTH WAYS on every covered bar ($what)." -ForegroundColor $(if ($liqPend -eq 0) { 'Green' } else { 'Yellow' })
        if ($pend -gt 0) { Write-Host "  (the pending pairs above are NOT included in this result)" -ForegroundColor Yellow }
    } else {
        Write-Host "  $($bad.Count) MISMATCH(ES) on covered bars:" -ForegroundColor Red
        $bad | Select-Object -First 20 | ForEach-Object { Write-Host ("    {0,-10} [{1}] {2}" -f $_.Side, $_.Pair, $_.Row) }
        $out = Join-Path $dir ("live_vs_build_diff_" + ($src -replace '[^A-Za-z0-9]','_') + ".txt")
        $bad | ForEach-Object { "{0,-10} {1} {2}" -f $_.Side, $_.Pair, $_.Row } | Set-Content $out
        Write-Host "  written to $out" -ForegroundColor Red
    }
}

function Show-Reload([string]$src) {
    $sel = @($blocks | Where-Object { $_.Src -eq $src })
    Write-Host "`n--- $src : comparing the last two builds ---" -ForegroundColor Cyan
    if ($sel.Count -lt 2) {
        Write-Host "  only $($sel.Count) block(s); 2 are needed." -ForegroundColor Red
        Write-Host "  force a rebuild on THAT chart: Ctrl+I -> HMI -> Properties -> OK." -ForegroundColor Yellow
        return
    }
    Compare-Builds $sel[-2] $sel[-1]
}

# A-52: fixed-window version regression. Two instances attached side by side
# (say v2.48 and v2.51 on two charts of one symbol) load the same window when
# they build within the same M5 bar; the log tells them apart by inst=, so
# they are two sources. Compare the last COMPLETE build of each.
function Show-Versus([string]$sa, [string]$sb) {
    Write-Host "`n--- $sa  vs  $sb : last complete build of each ---" -ForegroundColor Cyan
    $A = @($blocks | Where-Object { $_.Src -eq $sa -and $_.Status -eq 'COMPLETE' }) | Select-Object -Last 1
    $B = @($blocks | Where-Object { $_.Src -eq $sb -and $_.Status -eq 'COMPLETE' }) | Select-Object -Last 1
    if (-not $A -or -not $B) {
        Write-Host ("  no complete build for {0} - nothing to compare." -f $(if (-not $A) { $sa } else { $sb })) -ForegroundColor Red
        return
    }
    Compare-Builds $A $B
}

function Compare-Builds($A, $B) {
    Write-Host "  A  $(BlockLabel $A)" -ForegroundColor $(if ($A.Status -eq 'COMPLETE') { 'Gray' } else { 'Red' })
    Write-Host "  B  $(BlockLabel $B)" -ForegroundColor $(if ($B.Status -eq 'COMPLETE') { 'Gray' } else { 'Red' })

    # A-48: an INCOMPLETE build is not evidence of anything. No verdict.
    if ($A.Status -ne 'COMPLETE' -or $B.Status -ne 'COMPLETE') {
        Write-Host "  INCOMPLETE build(s) - no verdict:" -ForegroundColor Red
        foreach ($w in (@($A.Why) + @($B.Why))) { Write-Host "    $w" -ForegroundColor Red }
        Write-Host "  (a build cut by the terminal, or a log that mixes two runs; rebuild and run this again)" -ForegroundColor Yellow
        return
    }
    # A-52: parameters first, for every comparison. A version regression on
    # two different parameter sets measures the parameters, not the version.
    $known = ($A.Params -ne '?' -and $B.Params -ne '?')
    if ($known -and $A.Params -ne $B.Params) {
        Write-Host "  NOT COMPARABLE - different parameters ($($A.Params) vs $($B.Params))." -ForegroundColor Yellow
        return
    }

    # Common region: after BOTH real warm-ups, up to the older end. When the
    # two windows start differently, state carried from before the later
    # start (a session, a cycle, a context leg) can still differ for a while;
    # the first -SettleHours are therefore PENDING REVIEW - reported, never
    # passed - rather than explained away.
    $rs = $A.WarmEnd; if ($B.WarmEnd -gt $rs) { $rs = $B.WarmEnd }
    $rs = $rs.AddMinutes(5)
    $moved = ($A.From -ne $B.From)
    if ($moved) { $rs = $rs.AddHours($SettleHours) }
    $re = $A.To; if ($B.To -lt $re) { $re = $B.To }; $re = $re.AddMinutes(5)
    $why = 'same window'; if ($moved) { $why = "window moved: both warm-ups + $SettleHours h settle" }
    if ($re -le $rs) {
        Write-Host ("  NOT COMPARABLE - no common region after both warm-ups{0} (A {1} .. {2}, B {3} .. {4})." -f `
                    $(if ($moved) { " + $SettleHours h" } else { '' }),
                    $A.From.ToString('yyyy.MM.dd HH:mm'), $A.To.ToString('yyyy.MM.dd HH:mm'),
                    $B.From.ToString('yyyy.MM.dd HH:mm'), $B.To.ToString('yyyy.MM.dd HH:mm')) -ForegroundColor Yellow
        return
    }
    Write-Host ("  common region: {0} .. {1}  ({2})" -f $rs.ToString('yyyy.MM.dd HH:mm'), $re.ToString('yyyy.MM.dd HH:mm'), $why)
    $inA = @($A.Rows | Where-Object { $t = RowTime $_; $t -ge $rs -and $t -le $re }); $inB = @($B.Rows | Where-Object { $t = RowTime $_; $t -ge $rs -and $t -le $re })
    $mA = @($inA | Where-Object { (RowKind $_) -eq 'MODEL' }); $mB = @($inB | Where-Object { (RowKind $_) -eq 'MODEL' })
    $lA = @($inA | Where-Object { (RowKind $_) -eq 'LIQ' });   $lB = @($inB | Where-Object { (RowKind $_) -eq 'LIQ' })
    Write-Host ("  events inside it: A {0} MODEL + {1} LIQ / B {2} MODEL + {3} LIQ" -f $mA.Count, $lA.Count, $mB.Count, $lB.Count)

    if ($A.Ver -ne $B.Ver) {
        # Not a repaint test at all: a MODEL regression check of the upgrade,
        # labelled as exactly that, and only with something to compare.
        Write-Host "  DIFFERENT VERSIONS ($($A.Ver) / $($B.Ver)) - not a repaint test; MODEL upgrade regression only." -ForegroundColor Yellow
        if ($mA.Count -eq 0 -and $mB.Count -eq 0) {
            Write-Host "  INSUFFICIENT SAMPLE - no MODEL row on either side in the common region; this proves nothing." -ForegroundColor Yellow
            return
        }
        $d = @(DiffRows $mA $mB)
        if ($d.Count) {
            Write-Host ("  upgrade regression: {0} difference(s) over {1} / {2} MODEL row(s)" -f $d.Count, $mA.Count, $mB.Count) -ForegroundColor Red
            $d | Select-Object -First 20 | ForEach-Object { Write-Host "    $($_.Side)  $($_.Row)" }
        } elseif ($moved -or -not $known) {
            Write-Host ("  upgrade regression: 0 difference(s) over {0} / {1} MODEL row(s) - PENDING REVIEW, not a pass:" -f $mA.Count, $mB.Count) -ForegroundColor Yellow
            if ($moved)      { Write-Host "    the windows start at different bars: state carried from before the later start may differ" -ForegroundColor Yellow
                               Write-Host "    use a fixed window: both versions side by side, then -Source <one> -Versus <other>" -ForegroundColor Yellow }
            if (-not $known) { Write-Host "    parameter digest not logged on one side (pre-v2.44)" -ForegroundColor Yellow }
        } else {
            Write-Host ("  upgrade regression: 0 difference(s) over {0} / {1} MODEL row(s), same window and parameters." -f $mA.Count, $mB.Count) -ForegroundColor Green
        }
        return
    }

    # A-47: LIQ rows are judged only between two builds whose liquidity
    # history was READY. A build that was WAITING had its pre-window levels
    # provisional, so its LIQ rows are PENDING - not a liquidity pass, and
    # not a reason to fail the MODEL rows, which are judged regardless.
    $liqCmp = ($A.Liq -ne 'WAITING' -and $B.Liq -ne 'WAITING')
    if (-not $liqCmp) { Write-Host ("  liquidity: build {0} was still WAITING for history - LIQ rows PENDING, MODEL rows compared" -f $(if ($A.Liq -eq 'WAITING') { $A.Build } else { $B.Build })) -ForegroundColor Yellow }
    elseif ($A.Liq -eq '?' -or $B.Liq -eq '?') { Write-Host "  liquidity state not logged (pre-v2.50 build): LIQ rows compared as before" -ForegroundColor DarkGray }

    $cls = @()
    foreach ($d in (DiffRows $A.Rows $B.Rows)) {
        $c = 'MISMATCH'
        if ((RowKind $d.Row) -eq 'LIQ' -and -not $liqCmp) { $c = 'pending (liquidity WAITING)' }
        elseif ($d.Time -lt $rs) { $c = 'pending (before region)' }
        elseif ($d.Time -gt $re) { $c = 'beyond one build' }
        $cls += [pscustomobject]@{ Class = $c; Side = $d.Side; Time = $d.Time; Row = $d.Row }
    }
    foreach ($g in ($cls | Group-Object Class | Sort-Object Name)) {
        $col = 'Yellow'; if ($g.Name -eq 'MISMATCH') { $col = 'Red' } elseif ($g.Name -eq 'beyond one build') { $col = 'DarkGray' }
        Write-Host ("    {0,-28} {1,4}" -f $g.Name, $g.Count) -ForegroundColor $col
    }
    $mm   = @($cls | Where-Object Class -eq 'MISMATCH')
    $pend = @($cls | Where-Object Class -eq 'pending (before region)')
    if ($mm.Count -gt 0) {
        Write-Host "  $($mm.Count) event(s) differ INSIDE the comparable region - repaint or non-determinism:" -ForegroundColor Red
        $mm | Select-Object -First 20 | ForEach-Object { Write-Host ("    {0}  {1}" -f $_.Side, $_.Row) }
    } elseif ($mA.Count -eq 0 -and $mB.Count -eq 0 -and ($lA.Count + $lB.Count) -eq 0) {
        Write-Host "  INSUFFICIENT SAMPLE - no event on either side inside the comparable region; nothing was compared." -ForegroundColor Yellow
    } elseif ($pend.Count -gt 0 -or -not $known -or $A.WarmEst -or $B.WarmEst) {
        Write-Host "  no difference inside the comparable region - PENDING REVIEW, not a pass:" -ForegroundColor Yellow
        if ($pend.Count)            { Write-Host "    $($pend.Count) difference(s) before the region need a look (see file)" -ForegroundColor Yellow }
        if (-not $known)            { Write-Host "    parameter digest not logged (pre-v2.44 build)" -ForegroundColor Yellow }
        if ($A.WarmEst -or $B.WarmEst) { Write-Host "    warm-up end estimated, not logged (pre-v2.44 build)" -ForegroundColor Yellow }
    } elseif ($liqCmp) {
        Write-Host ("  IDENTICAL inside the comparable region ({0} MODEL + {1} LIQ) - no repaint found there." -f $mA.Count, $lA.Count) -ForegroundColor Green
    } else {
        Write-Host ("  MODEL IDENTICAL inside the comparable region ({0} rows) - no repaint found there." -f $mA.Count) -ForegroundColor Green
        Write-Host "  LIQ not judged: liquidity history was WAITING in one build - liquidity PENDING, rebuild once it is READY." -ForegroundColor Yellow
    }
    if ($cls.Count) {
        $out = Join-Path $dir ("reload_diff_" + ($A.Src -replace '[^A-Za-z0-9]','_') + ".txt")
        $cls | ForEach-Object { "{0,-28} {1,-7} {2}" -f $_.Class, $_.Side, $_.Row } | Set-Content $out
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
    Write-Host "  -Source `"<a>`" -Versus `"<b>`"   fixed-window version regression (two sources)" -ForegroundColor Yellow
    exit
}

if ($Versus -ne "") {
    if ($Source -eq "") { Write-Host "`n-Versus needs -Source: -Source <one source> -Versus <the other>" -ForegroundColor Red; exit }
    if ($sources.Name -notcontains $Versus) { Write-Host "`n'$Versus' is not one of the sources above." -ForegroundColor Red; exit }
    Show-Versus $Source $Versus
    exit
}
foreach ($t in $targets) {
    if     ($Rejects)     { Show-Rejects      $t }
    elseif ($LiveVsBuild) { Show-LiveVsBuild  $t }
    else                  { Show-Reload       $t }
}
