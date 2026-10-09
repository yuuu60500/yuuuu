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
#  (v2.53) H4 structure events (HMI-CTX) are a third judged category next to
#  MODEL and LIQ: reload and live-vs-rebuild must agree on them too. Between
#  two VERSIONS every difference gets one of three verdicts (A-57):
#    explained            a concrete link: the swing the newer build had
#                         already processed, the H4 direction that gates this
#                         POI / session, the upstream item this one hangs on
#    UNEXPLAINED          provably not the de-dup: H4 data that differs, a
#                         strength the rule cannot give, anything before the
#                         first de-dup / first H4 direction difference, a model
#                         whose cycle is identical and open in both builds
#    PENDING_ATTRIBUTION  neither: listed for a manual conclusion
#  Only "every difference explained" is a pass; time order alone explains nothing.
#  (A-58) A link is not enough either: before anything upstream may explain a
#  SESS / BLK / ARM / MODEL row, the row must sit inside its parent's lifetime
#  in its own build (session start..end, block confirm, the cycle from its
#  ARMED to the next ARMED), by the indicator's phase order. A row outside it
#  is UNEXPLAINED; a parent, time or end that is not in the log leaves it
#  PENDING_ATTRIBUTION. A session end explains only what comes after it.
#
#     -NoArmedBarPA     the builds ran with InpPAAllowArmedBarConfirm = false
#                       (D-4 off): then no model may confirm on its ARMED bar.
#                       Default: D-4 on, the indicator default - PA ENGULFING /
#                       REJECTION may confirm on the ARMED bar, nothing else.
#     -H4SwingRight 2   (A-61, -Ctx) InpH4SwingRight of the builds read; the
#                       stale-BOS check needs it to know when a swing was confirmed.
#                       Default 2, the indicator default.
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
      [int]$SettleHours = 24, [string]$Versus = "", [switch]$NoArmedBarPA, [int]$H4SwingRight = 2)

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
# ---- v2.53 structure rows (A-56) ----------------------------------------------
# HMI-CTX: one row per H4 structure event. Its key leaves out live= (live vs
# rebuild) and also= (v2.52 does not log it); everything else must agree.
function CtxParse([string]$msg) {
    $c = $msg -split ','
    if ($c.Count -lt 4) { return $null }
    $f = @{}; foreach ($p in $c[3..($c.Count-1)]) { $kv = $p -split '=', 2; if ($kv.Count -eq 2) { $f[$kv[0]] = $kv[1] } }
    $ev = "{0}|{1}|{2}|{3}|messy={4}" -f $f['bar'], $c[2], $f['dir'], $f['ctx'], $f['messy']
    [pscustomobject]@{ Kind = $c[2]; Dir = $f['dir']; Ctx = $f['ctx']; Bar = (PT16 $f['bar']); BarS = $f['bar']; Swing = $f['swing']
                       Str = $f['str']; Close = $f['close']; SwPx = $f['swing_px']
                       Key = "$ev|str=$($f['str'])|$($f['swing'])|$($f['swing_px'])|$($f['close'])"
                       KeyNoStr = "$ev|$($f['swing'])|$($f['swing_px'])|$($f['close'])"
                       Event = $ev }
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
    $bk = [pscustomobject]@{ Src = $src; Head = $head; Rows = (New-Object System.Collections.ArrayList); Lines = (New-Object System.Collections.ArrayList); Tail = ''
                       Ver = $v; Params = $(if ($m.ContainsKey('params')) { $m['params'] } else { '?' })
                       Inst = $(if ($m.ContainsKey('inst')) { $m['inst'].ToUpper() } else { '?' })
                       Id = $id; Build = $(if ($m.ContainsKey('build')) { $m['build'] } else { '?' })
                       From = (PT16 $m['from']); To = (PT16 $m['to']); FromS = $m['from']; ToS = $m['to']
                       WarmEnd = $we; WarmEst = $west; WarmS = $ws; BeginIdx = $idx; EndIdx = -1
                       Liq = '?'; LiqEv = -1; Marks = -1; Unknown = -1; LiqWait = -1; ModelN = 0; LiqN = 0
                       Status = 'OPEN'; Why = (New-Object System.Collections.ArrayList); BadRows = 0
                       Strict = $strict; V251 = ($vn -ge [decimal]2.51); NoIdRows = 0; BadKinds = @{}
                       BuildReq = ($strict -or $vn -ge [decimal]2.44); BuildOk = $false }
    # A-54: from v2.44 on every BEGIN carries build=, a positive integer. A
    # missing or malformed one used to read as '?' - and '?' on both BEGIN and
    # END compared equal, so a build with no number at all could still pass.
    $bk.BuildOk = ValidBuild $bk.Build
    if ($bk.BuildReq -and -not $bk.BuildOk) { [void]$bk.Why.Add("BEGIN without a valid build= ($(BuildShown $m))") }
    return $bk
}
function ValidBuild([string]$b) { return ($b -match '^[1-9][0-9]{0,9}$') }
function BuildShown($kv) { if ($kv.ContainsKey('build')) { return $kv['build'] } return 'missing' }
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

$blocks = @(); $open = @{}; $verNow = @{}; $liveAll = @(); $liveCtx = @(); $orphanRows = 0; $orphanEnds = 0
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
        if ($bk.BuildReq) {
            if (-not (ValidBuild $eb)) { [void]$bk.Why.Add("END without a valid build= ($(BuildShown $e))") }
            elseif ($bk.BuildOk -and $eb -ne $bk.Build) { [void]$bk.Why.Add("END build=$eb, BEGIN build=$($bk.Build)") }
        }
        elseif ($eb -ne $bk.Build) { [void]$bk.Why.Add("END build=$eb, BEGIN build=$($bk.Build)") }      # pre-v2.44 log
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
    elseif ($msg -match '^HMI-CTX,') {                          # a structure event outside a build = live
        $cr = CtxParse $msg
        if ($cr) { $liveCtx += [pscustomobject]@{ Src = $src; Idx = $i; Id = $id; C = $cr } }
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

# A-61: the break margin each chart logs at start-up, in points. ATR mode logs
# no number (per bar) -> -1. Two different values for one symbol -> -1 too:
# which one a given build used is then not in the log.
$margin = @{}
foreach ($l in $all) {
    if ($l -match '\(([A-Za-z0-9._#]+),[A-Za-z0-9]+\)\s+HMI: effective break margin = [0-9.]+ price / (\d+) points') {
        $sy = $Matches[1]; $pt = [int]$Matches[2]
        if ($margin.ContainsKey($sy) -and $margin[$sy] -ne $pt) { $margin[$sy] = -1 } else { $margin[$sy] = $pt }
    } elseif ($l -match '\(([A-Za-z0-9._#]+),[A-Za-z0-9]+\)\s+HMI: break margin mode = ATR_FRAC') { $margin[$Matches[1]] = -1 }
}
function PxDigits([string]$px) { $i = $px.IndexOf('.'); if ($i -lt 0) { return 0 } return $px.Length - $i - 1 }
function HasWeekend([datetime]$a, [datetime]$b) {
    for ($d = $a.Date; $d -le $b.Date; $d = $d.AddDays(1)) { if ($d.DayOfWeek -eq 'Saturday' -or $d.DayOfWeek -eq 'Sunday') { return $true } }
    return $false
}
# Did any earlier close of this leg break e's swing, as the engine judges it?
function StaleVerdict($e, $legC, [string]$ldir, $mg) {
    $ts = PT16 $e.Swing
    if ($ts -eq [datetime]::MinValue) { return [pscustomobject]@{ V = 'PENDING'; Why = 'swing time not logged' } }
    $earliest = $ts.AddHours(4 * ($H4SwingRight + 1))      # confirmation close, no gap
    $pt = [Math]::Pow(10, -(PxDigits $e.SwRaw))
    $pend = $null
    foreach ($c in $legC) {
        $tc = PT16 $c.Bar                                    # close time of that event's H4 bar
        if ($tc -lt $earliest) { continue }                  # swing not confirmed yet: new structure for that close
        $d = [Math]::Round($(if ($ldir -eq 'UP') { $c.Close - $e.SwPx } else { $e.SwPx - $c.Close }) / $pt)
        if ($d -le 0) { continue }                            # did not even reach past the raw price
        if ($mg -eq $null) { $pend = "close $($c.CloseRaw) at $($c.Bar) is $d pt past it, the margin is not in the log"; continue }
        if ($mg -lt 0)     { $pend = "close $($c.CloseRaw) at $($c.Bar) is $d pt past it, the margin is per bar (ATR)"; continue }
        if ($d -le $mg)    { continue }                       # within the margin: not an effective break
        $sure = (-not (HasWeekend $ts $tc)) -or ($tc -ge $earliest.AddHours(72))
        if ($sure) { return [pscustomobject]@{ V = 'STALE'; Why = "close $($c.CloseRaw) at $($c.Bar) broke it by $d pt > margin $mg after its confirmation" } }
        $pend = "close $($c.CloseRaw) at $($c.Bar) is $d pt past it, but a weekend lies between swing and close: confirmation time not provable"
    }
    if ($pend) { return [pscustomobject]@{ V = 'PENDING'; Why = $pend } }
    return [pscustomobject]@{ V = 'OK'; Why = '' }
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
            Bar = $f['bar']; Swing = $f['swing']; SwPx = $swp; Close = $cls; SwRaw = [string]$f['swing_px']; CloseRaw = [string]$f['close']
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

        # A-33 signature (A-61): a continuation BOS re-counts an old level only
        # when an EARLIER close in the same leg had already broken that swing,
        # as the context engine itself judges a break:
        #   1. the swing was CONFIRMED when that close happened - a swing the
        #      engine could not see yet is new structure, not an old level;
        #   2. that close cleared it by MORE than the break margin (strict,
        #      integer points) - touching or poking past the raw price is no break.
        # The log has the swing's bar time, not its confirmation time: confirmation
        # is (H4SwingRight + 1) H4 bars later, or later still across a weekend /
        # holiday gap. A close before the earliest possible confirmation proves
        # "not confirmed"; one after it proves "confirmed" only with no Saturday /
        # Sunday in between (or 72 h of slack). Anything the log cannot settle -
        # a gap, a per-bar ATR margin, an unknown margin - is PENDING, never a
        # re-count. Closes are only those of logged events: a LOWER bound.
        $mg = $(if ($margin.ContainsKey($g.Name)) { $margin[$g.Name] } else { $null })   # points; -1 = per bar (ATR); $null = not logged
        $stale = 0; $pendS = 0; $bosN = 0; $legC = $null; $ldir = ''; $staleWhy = @()
        foreach ($e in $ev) {
            if ($e.Kind -eq 'BOS' -and $e.Str -gt 1 -and $legC -ne $null -and $e.Dir -eq $ldir) {
                $bosN++
                $v = StaleVerdict $e $legC $ldir $mg
                if ($v.V -eq 'STALE') { $stale++; $staleWhy += "STALE    $($e.Bar) swing $($e.Swing) @ $($e.SwRaw): $($v.Why)" }
                elseif ($v.V -eq 'PENDING') { $pendS++; $staleWhy += "PENDING  $($e.Bar) swing $($e.Swing) @ $($e.SwRaw): $($v.Why)" }
                [void]$legC.Add($e)
            }
            elseif ($e.Kind -eq 'BOS' -or $e.Kind -eq 'TRANS_OK' -or $e.Kind -eq 'TRANS_FAIL') {
                $legC = New-Object System.Collections.ArrayList; [void]$legC.Add($e); $ldir = $e.Dir   # a leg begins here
            }
            else { $legC = $null; $ldir = '' }        # CHOCH / SAMELEG / TIMEOUT
        }
        if ($bosN -gt 0) {
            $mgS = $(if ($mg -eq $null) { 'margin not logged' } elseif ($mg -lt 0) { 'margin per bar (ATR)' } else { "margin $mg pt" })
            Write-Host ("      A-33 stale BOS  {0} re-count(s), {1} pending, of {2} continuation BOS  ({3}, H4SwingRight {4})" -f `
                        $stale, $pendS, $bosN, $mgS, $H4SwingRight) -ForegroundColor $(if ($stale -gt 0) { 'Red' } elseif ($pendS -gt 0) { 'Yellow' } else { 'Green' })
            $staleWhy | Select-Object -First 8 | ForEach-Object { Write-Host "        $_" -ForegroundColor $(if ($_ -like 'STALE*') { 'Red' } else { 'Yellow' }) }
            if ($staleWhy.Count -gt 8) { Write-Host "        ... $($staleWhy.Count - 8) more" -ForegroundColor Yellow }
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
# Multiset difference of objects carrying .Key: what each side has more of.
function DiffKeys($a, $b, [string]$prop = 'Key') {
    $ca = @{}; $cb = @{}
    foreach ($x in $a) { $k = $x.$prop; if (-not $ca.ContainsKey($k)) { $ca[$k] = New-Object System.Collections.ArrayList }; [void]$ca[$k].Add($x) }
    foreach ($x in $b) { $k = $x.$prop; if (-not $cb.ContainsKey($k)) { $cb[$k] = New-Object System.Collections.ArrayList }; [void]$cb[$k].Add($x) }
    $oa = New-Object System.Collections.ArrayList; $ob = New-Object System.Collections.ArrayList
    foreach ($k in $ca.Keys) { $n = $ca[$k].Count - $(if ($cb.ContainsKey($k)) { $cb[$k].Count } else { 0 }); for ($j = 0; $j -lt $n; $j++) { [void]$oa.Add($ca[$k][$j]) } }
    foreach ($k in $cb.Keys) { $n = $cb[$k].Count - $(if ($ca.ContainsKey($k)) { $ca[$k].Count } else { 0 }); for ($j = 0; $j -lt $n; $j++) { [void]$ob.Add($cb[$k][$j]) } }
    return [pscustomobject]@{ A = $oa; B = $ob }
}

# Structure rows of one build, read once: CTX events, the swings this build
# processed (as primary, or from v2.53 de-duplicated with one), and the chain
# POI -> SESS -> BLK -> ARM with the ids that link them INSIDE the build. Ids
# are init-relative, so across builds every item is named by stable fields:
#   POI   dir|origin|lo|hi                     SESS  POI|start bar
#   BLK   SESS|dir|type|counter|confirm bar    ARM   BLK|armed bar
function KVfrom([string[]]$c, [int]$from) { $f = @{}; for ($i = $from; $i -lt $c.Count; $i++) { $kv = $c[$i] -split '=', 2; if ($kv.Count -eq 2) { $f[$kv[0]] = $kv[1] } }; return $f }
function Get-Struct($bk) {
    if ($bk.PSObject.Properties['Struct']) { return $bk.Struct }
    $ctx = New-Object System.Collections.ArrayList; $proc = @{}; $dedupN = 0; $tDedup = [datetime]::MaxValue
    $poiById = @{}; $sessById = @{}; $blkById = @{}
    $poi = New-Object System.Collections.ArrayList; $sess = New-Object System.Collections.ArrayList
    $blk = New-Object System.Collections.ArrayList; $arm = New-Object System.Collections.ArrayList
    foreach ($m in $bk.Lines) {
        if ($m -match '^HMI-CTX,') {
            $r = CtxParse $m
            if ($r) { [void]$ctx.Add($r); if ($r.Swing) { $k = "$($r.Dir)|$($r.Swing)"; if (-not $proc.ContainsKey($k)) { $proc[$k] = $r.Bar } } }
            continue
        }
        if ($m -match '^HMI-CTX-DEDUP,') {
            $f = KVfrom ($m -split ',') 3
            $bar = PT16 $f['bar']; $dedupN++; if ($bar -lt $tDedup) { $tDedup = $bar }
            foreach ($s in ([string]$f['swings'] -split '\|')) {
                $st = ($s -split '@')[0]; $k = "$($f['dir'])|$st"
                if ($st -and -not $proc.ContainsKey($k)) { $proc[$k] = $bar }
            }
            continue
        }
        if ($m -notmatch '^HMI-(POI|SESS|BLK|ARM),') { continue }
        $c = $m -split ','; $f = KVfrom $c 2; $t = PT16 $f['bar']
        switch -regex ($m) {
            '^HMI-POI,[^,]*,NEW,' {
                $key = "$($f['dir'])|$($f['origin'])|$($f['lo'])|$($f['hi'])"
                $poiById[$f['id']] = $key
                [void]$poi.Add([pscustomobject]@{ Kind = 'NEW'; P = $key; Dir = [int]$f['dir']; Time = $t; Key = "NEW|$key|$($f['bar'])" })
                break }
            '^HMI-POI,[^,]*,(INVALID|EXPIRED|OUT),' {
                $kind = $c[2]; $key = $(if ($poiById.ContainsKey($f['id'])) { $poiById[$f['id']] } else { "?id$($f['id'])" })
                [void]$poi.Add([pscustomobject]@{ Kind = $kind; P = $key; Dir = [int]$f['dir']; Time = $t; Key = "$kind|$key|$($f['bar'])" })
                break }
            '^HMI-SESS,[^,]*,START,' {
                $pk = $(if ($poiById.ContainsKey($f['poi'])) { $poiById[$f['poi']] } else { "?id$($f['poi'])" })
                $sk = "$pk|$($f['bar'])"; $sessById[$f['id']] = $sk
                [void]$sess.Add([pscustomobject]@{ Kind = 'START'; S = $sk; P = $pk; Dir = [int]$f['dir']; Time = $t; Reason = ''; Key = "START|$sk" })
                break }
            '^HMI-SESS,[^,]*,END,' {
                $sk = $(if ($sessById.ContainsKey($f['id'])) { $sessById[$f['id']] } else { "?id$($f['id'])" })
                [void]$sess.Add([pscustomobject]@{ Kind = 'END'; S = $sk; P = ''; Dir = [int]$f['dir']; Time = $t; Reason = $f['reason']; Key = "END|$sk|$($f['reason'])|$($f['bar'])" })
                break }
            '^HMI-BLK,' {
                $sk = $(if ($sessById.ContainsKey($f['sess'])) { $sessById[$f['sess']] } else { "?id$($f['sess'])" })
                $bkey = "$sk|$($f['dir'])|$($f['type'])|$($f['counter'])|$($f['bar'])"; $blkById[$f['id']] = $bkey
                [void]$blk.Add([pscustomobject]@{ B = $bkey; S = $sk; Dir = [int]$f['dir']; Time = $t; Key = $bkey })
                break }
            '^HMI-ARM,' {
                $bkey = $(if ($blkById.ContainsKey($f['block'])) { $blkById[$f['block']] } else { "?id$($f['block'])" })
                [void]$arm.Add([pscustomobject]@{ A = "$bkey|$($f['bar'])"; B = $bkey; BlockId = $f['block']; Dir = [int]$f['dir']; Time = $t; Key = "$bkey|$($f['bar'])" })
                break }
        }
    }
    # MODEL rows: column 4 is the block id = the cycle's anchor (Spec 9.1)
    $models = New-Object System.Collections.ArrayList
    foreach ($r in $bk.Rows) { if ((RowKind $r) -eq 'MODEL') { $c = $r -split ','; [void]$models.Add([pscustomobject]@{ Row = $r; Key = (Key $r); BlockId = $c[4]; Dir = [int]$c[2]; Name = $c[6]; Time = (RowTime $r) }) } }
    # lifetimes (A-58): first START / END per session, sessions in start order,
    # blocks by key, ARMED rows per block and in time order, POI creation
    $sessStart = @{}; $sessEnd = @{}
    foreach ($x in $sess) { if ($x.Kind -eq 'START') { if (-not $sessStart.ContainsKey($x.S)) { $sessStart[$x.S] = $x } } elseif (-not $sessEnd.ContainsKey($x.S)) { $sessEnd[$x.S] = $x } }
    $blkBy = @{}; foreach ($x in $blk) { if (-not $blkBy.ContainsKey($x.B)) { $blkBy[$x.B] = $x } }
    $armOf = @{}; foreach ($x in @($arm | Sort-Object Time)) { if (-not $armOf.ContainsKey($x.BlockId)) { $armOf[$x.BlockId] = New-Object System.Collections.ArrayList }; [void]$armOf[$x.BlockId].Add($x) }
    $poiNew = @{}; foreach ($x in $poi) { if ($x.Kind -eq 'NEW' -and -not $poiNew.ContainsKey($x.P)) { $poiNew[$x.P] = $x } }
    $s = [pscustomobject]@{ Ctx = $ctx; Proc = $proc; DedupN = $dedupN; TDedup = $tDedup
                            Poi = $poi; Sess = $sess; Blk = $blk; Arm = $arm; Models = $models
                            SessStart = $sessStart; SessEnd = $sessEnd; Starts = @($sess | Where-Object { $_.Kind -eq 'START' } | Sort-Object Time)
                            BlkBy = $blkBy; ArmOf = $armOf; ArmSorted = @($arm | Sort-Object Time); PoiNew = $poiNew }
    $bk | Add-Member -NotePropertyName Struct -NotePropertyValue $s -Force
    return $s
}

# H4 state of a build at every event bar: RANGE until its first event.
# Returns the divergence intervals between two builds (start, end, stateA, stateB).
function StateDivergence($ca, $cb) {
    $ta = @($ca | Sort-Object Bar); $tb = @($cb | Sort-Object Bar)
    $times = @(@($ta | ForEach-Object Bar) + @($tb | ForEach-Object Bar) | Sort-Object -Unique)
    $ia = 0; $ib = 0; $sa = 'RANGE'; $sb = 'RANGE'; $out = @(); $cur = $null
    foreach ($t in $times) {
        while ($ia -lt $ta.Count -and $ta[$ia].Bar -le $t) { $sa = $ta[$ia].Ctx; $ia++ }
        while ($ib -lt $tb.Count -and $tb[$ib].Bar -le $t) { $sb = $tb[$ib].Ctx; $ib++ }
        if ($sa -ne $sb) { if (-not $cur) { $cur = [pscustomobject]@{ From = $t; To = $t; A = $sa; B = $sb } } else { $cur.To = $t } }
        elseif ($cur) { $cur.To = $t; $out += $cur; $cur = $null }
    }
    if ($cur) { $cur | Add-Member -NotePropertyName Open -NotePropertyValue $true; $out += $cur }     # still different at the build's last event
    return ,$out
}

function DirOfCtx([string]$c) { if ($c -eq 'BULLISH') { return 1 } if ($c -eq 'BEARISH') { return -1 } return 0 }
# Trend direction the chain saw at time t. H4 events at bar <= t apply to an
# H4-side item (a POI is made on its own H4 bar, after Phase 0); an M5 item at
# close time t was processed by the M5 bar that opened at t - 5 min, which
# had consumed only the H4 bars closed by then.
function DirAt($ctxSorted, [datetime]$t, [bool]$m5) {
    $lim = $(if ($m5) { $t.AddMinutes(-5) } else { $t }); $d = 0
    foreach ($r in $ctxSorted) { if ($r.Bar -le $lim) { $d = DirOfCtx $r.Ctx } else { break } }
    return $d
}

# The strength rule as the context engine applies it (Spec 2.4): BOS from
# RANGE = 1, BOS in a trend +1, CHOCH = 0, TRANS_OK / TRANS_FAIL = 1,
# TRANS_SAMELEG / TIMEOUT leave it. Annotates every row with the value the
# rule gives and the bar its leg began; returns the rows whose logged str
# the rule cannot give.
function StrengthCheck($rows) {
    $prev = 'RANGE'; $str = 0; $leg = [datetime]::MinValue; $bad = @()
    foreach ($r in $rows) {
        switch ($r.Kind) {
            'BOS'        { if ($prev -eq 'BULLISH' -or $prev -eq 'BEARISH') { $str++ } else { $str = 1; $leg = $r.Bar } }
            'CHOCH'      { $str = 0; $leg = $r.Bar }
            'TRANS_OK'   { $str = 1; $leg = $r.Bar }
            'TRANS_FAIL' { $str = 1; $leg = $r.Bar }
        }
        $r | Add-Member -NotePropertyName StrRule -NotePropertyValue $str -Force
        $r | Add-Member -NotePropertyName Leg -NotePropertyValue $leg -Force
        if ([string]$r.Str -ne [string]$str) { $bad += $r }
        $prev = $r.Ctx
    }
    return ,$bad
}

function ObjId($o) { return [string][System.Runtime.CompilerServices.RuntimeHelpers]::GetHashCode($o) }

# ---- A-58: lifetimes ---------------------------------------------------------
# A chain row is a child of the row above it. Knowing WHICH parent (ids inside
# a build, stable keys across builds) does not show the parent existed, or was
# still alive, when the child happened. The bounds below are the indicator's
# own phase order (ProcessClosedM5Bar), all times as logged (bar CLOSE):
#   0b SessionMaintain: POI_INVALID / CONTEXT_FLIP / CONTEXT_NEUTRAL / TIMEOUT
#      end the session BEFORE Phase 1 of that bar
#   1  M5BlocksOnFVG: a block only while the session is active; its confirm
#      time is this bar's close, after the session's start bar (Spec 5.2:
#      confirm_time >= session start - only the OB's origin candle may be older)
#   3  SessionStart: NEW_SESSION ends the old one AFTER Phase 1 of that bar
#   4  models of the active cycle only for n > A, A = its ARMED bar
#   5  ARMED: a block confirmed on an EARLIER bar (anti-leak), of the ACTIVE
#      session, in the session's direction; it closes the previous cycle, so
#      that cycle's last models are the ones Phase 4 found on this same bar
#   5b on the ARMED bar itself only PA ENGULFING / PA REJECTION, and only
#      with D-4 on (InpPAAllowArmedBarConfirm, Spec 9.5.1)
# A cycle outlives its session (Rule 15): a model may follow the session end.
function SessBounds($s, [string]$sk) {
    if (-not $sk -or -not $s.SessStart.ContainsKey($sk)) { return $null }
    $st = $s.SessStart[$sk]; $en = $null; $nx = $null
    if ($s.SessEnd.ContainsKey($sk)) { $en = $s.SessEnd[$sk] }
    else { foreach ($o in $s.Starts) { if ($o.Time -gt $st.Time) { $nx = $o; break } } }
    return [pscustomobject]@{ Start = $st; End = $en; NextStart = $nx }
}
function T16([datetime]$t) { return $t.ToString('yyyy.MM.dd HH:mm') }
# The ARMED row that opened a model's cycle: the block's last ARMED at or
# before the model (a block arms once; $null = every ARMED is later).
function CycleArm($s, $x) {
    $a = $null
    if ($s.ArmOf.ContainsKey($x.BlockId)) { foreach ($c in $s.ArmOf[$x.BlockId]) { if ($c.Time -le $x.Time) { $a = $c } } }
    return $a
}
# $null when the row fits its parents' lifetimes in its own build; else
# UNEXPLAINED (a bound the indicator cannot break is broken) or
# PENDING_ATTRIBUTION (a parent, a time or an end is not in the log).
function ChainLife($s, [string]$type, $x) {
    $bad  = { param([string]$w) [pscustomobject]@{ V = 'UNEXPLAINED'; Why = $w } }
    $miss = { param([string]$w) [pscustomobject]@{ V = 'PENDING_ATTRIBUTION'; Why = $w } }
    if ($x.Time -eq [datetime]::MinValue) { return & $miss 'the row carries no time' }
    $unended = { param($w) "its session (start $(T16 $w.Start.Time)) has no END row although the session at $(T16 $w.NextStart.Time) started later: when it ended is not in the log" }
    switch ($type) {
        'SESS' {
            if ($x.Kind -eq 'START') {
                if ($x.P.StartsWith('?') -or -not $s.PoiNew.ContainsKey($x.P)) { return & $miss "its POI's NEW row is not in this build" }
                $p = $s.PoiNew[$x.P]
                if ($p.Time -ge $x.Time) { return & $bad "starts $(T16 $x.Time) on a POI confirmed $(T16 $p.Time): a POI is touched only after its confirm bar" }
                return $null
            }
            if (-not $s.SessStart.ContainsKey($x.S)) { return & $miss "its session's START row is not in this build" }
            $st = $s.SessStart[$x.S]
            if ($st.Time -ge $x.Time) { return & $bad "ends $(T16 $x.Time), not after its start $(T16 $st.Time)" }
            return $null
        }
        'BLK' {
            $w = SessBounds $s $x.S
            if (-not $w) { return & $miss "its session's START row is not in this build" }
            if ($x.Time -lt $w.Start.Time) { return & $bad "confirmed $(T16 $x.Time), before its session started $(T16 $w.Start.Time) (Spec 5.2: confirm_time >= session start)" }
            if ($w.End) {
                if ($w.End.Reason -eq 'NEW_SESSION') {
                    if ($x.Time -gt $w.End.Time) { return & $bad "confirmed $(T16 $x.Time), after its session ended $(T16 $w.End.Time) (NEW_SESSION)" }
                } elseif ($x.Time -ge $w.End.Time) {
                    return & $bad "confirmed $(T16 $x.Time), but its session ended $(T16 $w.End.Time) ($($w.End.Reason)) - Phase 0b ends it before Phase 1 makes any block on that bar"
                }
            } elseif ($w.NextStart) { return & $miss (& $unended $w) }
            return $null
        }
        'ARM' {
            if ($x.B.StartsWith('?') -or -not $s.BlkBy.ContainsKey($x.B)) { return & $miss "its block's NEW row is not in this build" }
            $b = $s.BlkBy[$x.B]
            if ($x.Time -le $b.Time) { return & $bad "ARMED $(T16 $x.Time), its block confirmed $(T16 $b.Time): a block is touched only on a later bar" }
            $w = SessBounds $s $b.S
            if (-not $w) { return & $miss "its block's session START row is not in this build" }
            if ($x.Time -le $w.Start.Time) { return & $bad "ARMED $(T16 $x.Time), its session started $(T16 $w.Start.Time)" }
            if ($w.End) {
                if ($x.Time -ge $w.End.Time) { return & $bad "ARMED $(T16 $x.Time), but its session ended $(T16 $w.End.Time) ($($w.End.Reason)) - Phase 5 arms only a block of the active session" }
            } elseif ($w.NextStart) { return & $miss (& $unended $w) }
            if ($x.Dir -ne $w.Start.Dir) { return & $bad "ARMED dir $($x.Dir) in a dir $($w.Start.Dir) session: only a block in the session's direction is armed" }
            return $null
        }
        'MODEL' {
            if (-not $s.ArmOf.ContainsKey($x.BlockId)) { return & $miss "its cycle's ARMED row (block $($x.BlockId)) is not in the log" }
            $a = CycleArm $s $x
            if (-not $a) { return & $bad "confirmed $(T16 $x.Time), before its cycle's ARMED $(T16 $s.ArmOf[$x.BlockId][0].Time): a cycle's models start at its ARMED bar (Phase 4: n > A)" }
            if ($x.Time -eq $a.Time) {
                if ($x.Name -ne 'PA ENGULFING' -and $x.Name -ne 'PA REJECTION') { return & $bad "$($x.Name) on its cycle's ARMED bar $(T16 $a.Time): Phase 4 needs n > A; only PA ENGULFING / REJECTION may confirm on bar A (D-4)" }
                if ($NoArmedBarPA) { return & $bad "$($x.Name) on its cycle's ARMED bar $(T16 $a.Time), and -NoArmedBarPA says D-4 was off" }
            }
            $nx = $null; foreach ($c in $s.ArmSorted) { if ($c.Time -gt $a.Time) { $nx = $c; break } }
            if ($nx -and $x.Time -gt $nx.Time) { return & $bad "confirmed $(T16 $x.Time), after the ARMED $(T16 $nx.Time) that closed its cycle (Rule 15; its last models are Phase 4 of that bar)" }
            if ($x.Dir -ne $a.Dir) { return & $bad "dir $($x.Dir), its cycle's ARMED dir $($a.Dir)" }
            return $null
        }
    }
    return $null
}

# A-57: why do two versions differ? Old = the lower version, New = the higher.
# Writes every verdict to attribution_<source>.txt and returns
# @{ Unexplained; Pending; Explained; ModelDiff }.
function Show-StructAttribution($Old, $New, [datetime]$rs, [datetime]$re) {
    $so = Get-Struct $Old; $sn = Get-Struct $New
    $lines = New-Object System.Collections.ArrayList
    $tally = [ordered]@{ explained = 0; PENDING_ATTRIBUTION = 0; UNEXPLAINED = 0 }
    $verdict = { param($v, [string]$what, [string]$why)
        $tally[$v]++; [void]$lines.Add(("{0,-20} {1}   <- {2}" -f $v, $what, $why)) }
    $tD = $sn.TDedup
    Write-Host ("  structure attribution (v{0} -> v{1}, whole build): CTX events {2} / {3}; de-duplicated bars in v{1}: {4}{5}" -f `
                $Old.Ver, $New.Ver, $so.Ctx.Count, $sn.Ctx.Count, $sn.DedupN,
                $(if ($sn.DedupN) { ", first " + $tD.ToString('yyyy.MM.dd HH:mm') } else { '' }))

    # ---- facts that no de-dup can change --------------------------------------
    $closeO = @{}; foreach ($r in $so.Ctx) { $closeO[$r.BarS] = $r.Close }
    $pxO = @{};    foreach ($r in $so.Ctx) { if ($r.Swing) { $pxO["$($r.Dir)|$($r.Swing)"] = $r.SwPx } }
    $dataBad = 0
    foreach ($r in $sn.Ctx) {
        if ($closeO.ContainsKey($r.BarS) -and $closeO[$r.BarS] -ne $r.Close) {
            $dataBad++; & $verdict 'UNEXPLAINED' "CTX $($r.Key)" "H4 close at $($r.BarS) is $($closeO[$r.BarS]) in v$($Old.Ver): the market data differs, the de-dup does not move a close"
        }
        $k = "$($r.Dir)|$($r.Swing)"
        if ($r.Swing -and $pxO.ContainsKey($k) -and $pxO[$k] -ne $r.SwPx) {
            $dataBad++; & $verdict 'UNEXPLAINED' "CTX $($r.Key)" "swing $($r.Swing) is $($pxO[$k]) in v$($Old.Ver): a swing's price is the data, not the de-dup"
        }
    }
    $badO = StrengthCheck $so.Ctx; $badN = StrengthCheck $sn.Ctx
    $badIds = @{}
    foreach ($r in @($badO) + @($badN)) {
        $badIds[(ObjId $r)] = 1
        & $verdict 'UNEXPLAINED' "CTX $($r.Key)" "str=$($r.Str) but the strength rule gives $($r.StrRule) from this build's own events"
    }

    # ---- CTX differences ---------------------------------------------------------
    $d0 = DiffKeys $so.Ctx $sn.Ctx 'KeyNoStr'
    $cls = [ordered]@{ 'suppressed duplicate' = 0; 'primary re-referenced' = 0; 'strength renumbered' = 0; 'PENDING_ATTRIBUTION' = 0; 'UNEXPLAINED' = 0 }
    $explainedCtx = @{}
    $newByEvent = @{}
    foreach ($y in $d0.B) { if (-not $newByEvent.ContainsKey($y.Event)) { $newByEvent[$y.Event] = New-Object System.Collections.ArrayList }; [void]$newByEvent[$y.Event].Add($y) }
    $paired = @{}
    foreach ($x in $d0.A) {
        if (-not $sn.DedupN -or $x.Bar -lt $tD) { $cls['UNEXPLAINED']++; & $verdict 'UNEXPLAINED' "CTX v$($Old.Ver) only $($x.Key)" 'before the first de-dup the two versions are the same code path'; continue }
        $k = "$($x.Dir)|$($x.Swing)"
        $dup = [bool]$x.Swing -and $sn.Proc.ContainsKey($k) -and $sn.Proc[$k] -lt $x.Bar
        $mate = $null
        if ($newByEvent.ContainsKey($x.Event)) { foreach ($y in $newByEvent[$x.Event]) { if (-not $paired.ContainsKey((ObjId $y))) { $mate = $y; break } } }
        if ($dup -and $mate -and $sn.Proc["$($mate.Dir)|$($mate.Swing)"] -eq $mate.Bar) {
            $paired[(ObjId $mate)] = 1; $cls['primary re-referenced']++; $explainedCtx[(ObjId $x)] = 1; $explainedCtx[(ObjId $mate)] = 1
            & $verdict 'explained' "CTX $($x.Key)  ->  $($mate.Key)" "same bar and event; v$($New.Ver) processed swing $($x.Swing) at $($sn.Proc[$k].ToString('yyyy.MM.dd HH:mm')), so the next swing this close breaks for the first time ($($mate.Swing)) is the primary"
        } elseif ($dup) {
            $cls['suppressed duplicate']++; $explainedCtx[(ObjId $x)] = 1
            & $verdict 'explained' "CTX v$($Old.Ver) only $($x.Key)" "swing $($x.Swing) was processed by v$($New.Ver) at $($sn.Proc[$k].ToString('yyyy.MM.dd HH:mm')) (de-dup): v$($Old.Ver) counts it again"
        } else {
            $cls['PENDING_ATTRIBUTION']++; & $verdict 'PENDING_ATTRIBUTION' "CTX v$($Old.Ver) only $($x.Key)" 'after a de-dup, but its swing was not processed earlier by the newer build and no paired event exists'
        }
    }
    foreach ($y in $d0.B) {
        if ($paired.ContainsKey((ObjId $y))) { continue }
        if (-not $sn.DedupN -or $y.Bar -lt $tD) { $cls['UNEXPLAINED']++; & $verdict 'UNEXPLAINED' "CTX v$($New.Ver) only $($y.Key)" 'before the first de-dup the two versions are the same code path'; continue }
        $cls['PENDING_ATTRIBUTION']++; & $verdict 'PENDING_ATTRIBUTION' "CTX v$($New.Ver) only $($y.Key)" 'after a de-dup, not paired with a duplicate the older build counted at this bar'
    }
    # same event, same swing, other str: explained only when both values follow
    # the rule, both legs start at the same event, and every BOS one leg has and
    # the other has not is itself an explained duplicate / re-reference
    $byO = @{}; foreach ($r in $so.Ctx) { if (-not $byO.ContainsKey($r.KeyNoStr)) { $byO[$r.KeyNoStr] = New-Object System.Collections.ArrayList }; [void]$byO[$r.KeyNoStr].Add($r) }
    $byN = @{}; foreach ($r in $sn.Ctx) { if (-not $byN.ContainsKey($r.KeyNoStr)) { $byN[$r.KeyNoStr] = New-Object System.Collections.ArrayList }; [void]$byN[$r.KeyNoStr].Add($r) }
    $legDiff = @(@($d0.A) + @($d0.B) | Where-Object { $_.Kind -eq 'BOS' })
    foreach ($k in $byO.Keys) {
        if (-not $byN.ContainsKey($k)) { continue }
        $n = [Math]::Min($byO[$k].Count, $byN[$k].Count)
        for ($j = 0; $j -lt $n; $j++) {
            $o = $byO[$k][$j]; $w = $byN[$k][$j]
            if ($o.Str -eq $w.Str) { continue }
            if ($badIds.ContainsKey((ObjId $o)) -or $badIds.ContainsKey((ObjId $w))) { continue }     # already UNEXPLAINED above
            $inLeg = @($legDiff | Where-Object { $_.Leg -eq $o.Leg -and $_.Bar -le $o.Bar })
            $allOk = (@($inLeg | Where-Object { -not $explainedCtx.ContainsKey((ObjId $_)) }).Count -eq 0)
            if ($o.Leg -eq $w.Leg -and $inLeg.Count -gt 0 -and $allOk) {
                $cls['strength renumbered']++
                & $verdict 'explained' "CTX $($o.Key)  ->  str=$($w.Str)" ("leg from {0}: {1} BOS counted by one version only, each an explained duplicate; both values follow the rule" -f $o.Leg.ToString('yyyy.MM.dd HH:mm'), $inLeg.Count)
            } else {
                $cls['PENDING_ATTRIBUTION']++
                & $verdict 'PENDING_ATTRIBUTION' "CTX $($o.Key)  ->  str=$($w.Str)" $(if ($o.Leg -ne $w.Leg) { 'the two legs start at different events' } else { 'the strength difference is not covered by explained duplicates in this leg' })
            }
        }
    }
    $cls['UNEXPLAINED'] += $dataBad + @($badO).Count + @($badN).Count
    foreach ($k in $cls.Keys) { Write-Host ("    CTX {0,-30} {1,5}" -f $k, $cls[$k]) -ForegroundColor $(if ($k -eq 'UNEXPLAINED' -and $cls[$k]) { 'Red' } elseif ($k -eq 'PENDING_ATTRIBUTION' -and $cls[$k]) { 'Yellow' } else { 'Gray' }) }

    # ---- H4 state / direction ----------------------------------------------------
    $div = StateDivergence $so.Ctx $sn.Ctx
    $co = @($so.Ctx | Sort-Object Bar); $cn = @($sn.Ctx | Sort-Object Bar)
    $tDir = [datetime]::MaxValue
    foreach ($iv in $div) { if ((DirOfCtx $iv.A) -ne (DirOfCtx $iv.B)) { $tDir = $iv.From; break } }
    if ($div.Count) {
        Write-Host ("    H4 state differs in {0} interval(s), first from {1}:" -f $div.Count, $div[0].From.ToString('yyyy.MM.dd HH:mm')) -ForegroundColor Yellow
        $div | Select-Object -First 10 | ForEach-Object {
            $till = $(if ($_.PSObject.Properties['Open']) { 'end of build    ' } else { 'before ' + $_.To.ToString('yyyy.MM.dd HH:mm') })
            Write-Host ("      {0} .. {1}   v{2} {3,-10}  v{4} {5}" -f $_.From.ToString('yyyy.MM.dd HH:mm'), $till, $Old.Ver, $_.A, $New.Ver, $_.B) }
    } else {
        Write-Host "    H4 state: identical at every event bar - so the chain below must be identical too" -ForegroundColor Gray
    }

    # ---- chain: POI -> SESS -> BLK -> ARM -> MODEL -------------------------------
    Write-Host ("    chain rows are checked against their parents' lifetimes first (A-58); D-4 (PA ENGULFING / REJECTION on the ARMED bar) {0}" -f `
                $(if ($NoArmedBarPA) { 'OFF (-NoArmedBarPA)' } else { 'ON, the indicator default (-NoArmedBarPA if the builds ran with it off)' })) -ForegroundColor DarkGray
    # Every chain item reads the H4 trend direction (POI creation, session
    # eligibility and end, the ARMED guard) or the item above it. Before the
    # first DIRECTION difference nothing in the chain can differ (UNEXPLAINED);
    # after it, a verdict needs the concrete link named in each rule below.
    $inR = { param($t) $t -ge $rs -and $t -le $re }
    $side = { param($x, $setA) if ($setA) { return @{ Has = $Old.Ver; Hasnt = $New.Ver; HasCtx = $co; NotCtx = $cn; HasS = $so; NotS = $sn } }
                                return @{ Has = $New.Ver; Hasnt = $Old.Ver; HasCtx = $cn; NotCtx = $co; HasS = $sn; NotS = $so } }
    $ex = @{}                                       # "TYPE|key" -> 1 for explained chain items ("SESSEND|ver|key" per build)
    $chainCount = [ordered]@{ POI = 0; SESS = 0; BLK = 0; ARM = 0; MODEL = 0 }
    $early = { param($t) $t -lt $tDir }
    # A-58: a row outside its parents' lifetime (own build) is UNEXPLAINED, a
    # row whose parent / time / end is missing is PENDING - checked BEFORE any
    # upstream verdict may carry over. A row whose own parent was judged
    # UNEXPLAINED is PENDING too: nothing hanging on an impossible row is
    # attributed. Returns $true when it gave the verdict.
    $taint = @{}                                    # "TYPE|key" of chain rows judged UNEXPLAINED
    $gate = { param([string]$type, $x, $sd, [string]$what, [string]$self, [string]$parent)
        $lf = ChainLife $sd.HasS $type $x
        if ($lf -and $lf.V -eq 'UNEXPLAINED') { if ($self) { $taint[$self] = 1 }; & $verdict 'UNEXPLAINED' $what "outside its parent's lifetime in v$($sd.Has): $($lf.Why)"; return $true }
        if (& $early $x.Time) { if ($self) { $taint[$self] = 1 }; & $verdict 'UNEXPLAINED' $what 'before the first H4 direction difference'; return $true }
        if ($lf) { & $verdict 'PENDING_ATTRIBUTION' $what $lf.Why; return $true }
        if ($parent -and $taint.ContainsKey($parent)) { & $verdict 'PENDING_ATTRIBUTION' $what "its parent row ($($parent -replace '\|.*$','')) is UNEXPLAINED above: nothing hanging on it is attributed"; return $true }
        return $false }
    # The other build's END of this session, when it is explained and came
    # early enough to keep this row out of that build: no block from the
    # session's end bar on (NEW_SESSION: from the next bar), no ARMED from it.
    $endBefore = { param($sd, [string]$sk, [datetime]$t, [bool]$isBlock)
        if (-not $sd.NotS.SessEnd.ContainsKey($sk)) { return $null }
        $e = $sd.NotS.SessEnd[$sk]
        if (-not $ex.ContainsKey("SESSEND|$($sd.Hasnt)|$sk")) { return $null }
        $ok = $(if ($isBlock -and $e.Reason -eq 'NEW_SESSION') { $e.Time -lt $t } else { $e.Time -le $t })
        return [pscustomobject]@{ End = $e; Before = $ok } }

    # POI events
    $pO = @{}; foreach ($p in $so.Poi) { if ($p.Kind -eq 'NEW') { $pO[$p.P] = $p } }
    $pN = @{}; foreach ($p in $sn.Poi) { if ($p.Kind -eq 'NEW') { $pN[$p.P] = $p } }
    $dP = DiffKeys @($so.Poi | Where-Object { & $inR $_.Time }) @($sn.Poi | Where-Object { & $inR $_.Time }) 'Key'
    $poiItems = @(@($dP.A | ForEach-Object { [pscustomobject]@{ X = $_; InOld = $true } }) + @($dP.B | ForEach-Object { [pscustomobject]@{ X = $_; InOld = $false } }) | Sort-Object { $_.X.Time }, { if ($_.X.Kind -eq 'NEW') { 0 } else { 1 } })
    $explainedNewTimes = @()
    $deferPoi = @()
    foreach ($it in $poiItems) {
        $x = $it.X; $sd = & $side $x $it.InOld; $chainCount.POI++
        $what = "POI v$($sd.Has) only $($x.Key)"
        if (& $early $x.Time) { if ($x.Kind -eq 'NEW') { $taint["POI|$($x.P)"] = 1 }; & $verdict 'UNEXPLAINED' $what 'before the first H4 direction difference'; continue }
        $inBoth = $pO.ContainsKey($x.P) -and $pN.ContainsKey($x.P)
        if ($x.Kind -eq 'NEW') {
            $dh = DirAt $sd.HasCtx $x.Time $false; $dn = DirAt $sd.NotCtx $x.Time $false
            if ($dh -ne $dn -and $dh -eq $x.Dir) { $ex["POI|$($x.P)"] = 1; $explainedNewTimes += $x.Time
                & $verdict 'explained' $what "a POI needs the H4 trend in its direction on its own bar: v$($sd.Has) $dh, v$($sd.Hasnt) $dn" }
            else { & $verdict 'PENDING_ATTRIBUTION' $what "H4 direction on its bar is the same in both ($dh) or not its own" }
        } elseif (-not $inBoth) {
            if ($ex.ContainsKey("POI|$($x.P)")) { & $verdict 'explained' $what 'the POI exists in one build only, and its creation is explained' }
            else { & $verdict 'PENDING_ATTRIBUTION' $what 'the POI exists in one build only and its creation is not explained' }
        } elseif ($x.Kind -eq 'OUT') {
            if (@($explainedNewTimes | Where-Object { $_ -le $x.Time }).Count) { $ex["POIEV|$($x.Key)"] = 1
                & $verdict 'explained' $what 'the POI window is first-in first-out: an explained POI made in one build only by then shifts it' }
            else { & $verdict 'PENDING_ATTRIBUTION' $what 'no explained POI difference before it to shift the window' }
        } else { $deferPoi += $it }                  # EXPIRED / INVALID of a POI in both: needs the sessions
    }

    # sessions
    $sessO = @{}; foreach ($s in $so.Sess) { if ($s.Kind -eq 'START') { $sessO[$s.S] = $s } }
    $sessN = @{}; foreach ($s in $sn.Sess) { if ($s.Kind -eq 'START') { $sessN[$s.S] = $s } }
    $dS = DiffKeys @($so.Sess | Where-Object { & $inR $_.Time }) @($sn.Sess | Where-Object { & $inR $_.Time }) 'Key'
    $sessItems = @(@($dS.A | ForEach-Object { [pscustomobject]@{ X = $_; InOld = $true } }) + @($dS.B | ForEach-Object { [pscustomobject]@{ X = $_; InOld = $false } }) | Sort-Object { $_.X.Time }, { if ($_.X.Kind -eq 'START') { 0 } else { 1 } })
    $explainedStartTimes = @()
    foreach ($it in $sessItems) {
        $x = $it.X; $sd = & $side $x $it.InOld; $chainCount.SESS++
        $what = "SESS v$($sd.Has) only $($x.Key)"
        $self = $(if ($x.Kind -eq 'START') { "SESS|$($x.S)" } else { '' }); $par = $(if ($x.Kind -eq 'START') { "POI|$($x.P)" } else { "SESS|$($x.S)" })
        if (& $gate 'SESS' $x $sd $what $self $par) { continue }
        if ($x.Kind -eq 'START') {
            $dh = DirAt $sd.HasCtx $x.Time $true; $dn = DirAt $sd.NotCtx $x.Time $true
            if ($ex.ContainsKey("POI|$($x.P)")) { $ex["SESS|$($x.S)"] = 1; $explainedStartTimes += $x.Time; & $verdict 'explained' $what 'its POI exists in one build only, explained' }
            elseif ($dh -ne $dn -and $dh -eq $x.Dir) { $ex["SESS|$($x.S)"] = 1; $explainedStartTimes += $x.Time
                & $verdict 'explained' $what "a session starts only with the H4 trend in its POI's direction: v$($sd.Has) $dh, v$($sd.Hasnt) $dn" }
            else { & $verdict 'PENDING_ATTRIBUTION' $what 'same POI in both, same H4 direction at the touch' }
        } else {
            $inBoth = $sessO.ContainsKey($x.S) -and $sessN.ContainsKey($x.S)
            if (-not $inBoth) {
                if ($ex.ContainsKey("SESS|$($x.S)")) { $ex["SESSEND|$($sd.Has)|$($x.S)"] = 1; & $verdict 'explained' $what 'the session exists in one build only, its start is explained' }
                else { & $verdict 'PENDING_ATTRIBUTION' $what 'the session exists in one build only and its start is not explained' }
                continue
            }
            $dh = DirAt $sd.HasCtx $x.Time $true; $dn = DirAt $sd.NotCtx $x.Time $true
            $oe = $(if ($sd.NotS.SessEnd.ContainsKey($x.S)) { $sd.NotS.SessEnd[$x.S] } else { $null })
            if (($x.Reason -eq 'CONTEXT_FLIP' -or $x.Reason -eq 'CONTEXT_NEUTRAL') -and $dh -ne $dn) { $ex["SESSEND|$($sd.Has)|$($x.S)"] = 1
                & $verdict 'explained' $what "ended by the H4 direction, which differs at that bar: v$($sd.Has) $dh, v$($sd.Hasnt) $dn" }
            elseif ($x.Reason -eq 'NEW_SESSION' -and @($explainedStartTimes | Where-Object { $_ -eq $x.Time }).Count) { $ex["SESSEND|$($sd.Has)|$($x.S)"] = 1
                & $verdict 'explained' $what 'ended by a new session whose start is explained' }
            elseif ($oe -and $oe.Time -lt $x.Time -and $ex.ContainsKey("SESSEND|$($sd.Hasnt)|$($x.S)")) { $ex["SESSEND|$($sd.Has)|$($x.S)"] = 1
                & $verdict 'explained' $what ("a session ends once: v{0} had already ended it at {1} ({2}, explained)" -f $sd.Hasnt, (T16 $oe.Time), $oe.Reason) }
            else { & $verdict 'PENDING_ATTRIBUTION' $what "same session in both, end ($($x.Reason)) not linked to an explained difference" }
        }
    }
    foreach ($it in $deferPoi) {
        $x = $it.X; $sd = & $side $x $it.InOld
        $what = "POI v$($sd.Has) only $($x.Key)"
        $touch = @(@($sessItems | Where-Object { $_.X.Kind -eq 'START' -and $_.X.P -eq $x.P -and $_.X.Time -le $x.Time -and $ex.ContainsKey("SESS|$($_.X.S)") })).Count
        if ($touch) { & $verdict 'explained' $what 'its POI was touched (session) in one build only by then, explained: only an untouched POI ages out' }
        else { & $verdict 'PENDING_ATTRIBUTION' $what 'same POI in both, no explained touch difference before it' }
    }

    # blocks and ARMED
    $dB = DiffKeys @($so.Blk | Where-Object { & $inR $_.Time }) @($sn.Blk | Where-Object { & $inR $_.Time }) 'Key'
    foreach ($it in @(@($dB.A | ForEach-Object { [pscustomobject]@{ X = $_; InOld = $true } }) + @($dB.B | ForEach-Object { [pscustomobject]@{ X = $_; InOld = $false } }))) {
        $x = $it.X; $sd = & $side $x $it.InOld; $chainCount.BLK++
        $what = "BLK v$($sd.Has) only $($x.Key)"
        if (& $gate 'BLK' $x $sd $what "BLK|$($x.B)" "SESS|$($x.S)") { continue }
        $eb = & $endBefore $sd $x.S $x.Time $true
        if ($ex.ContainsKey("SESS|$($x.S)")) { $ex["BLK|$($x.B)"] = 1; & $verdict 'explained' $what 'blocks are made only inside their own session, which exists in one build only (start explained)' }
        elseif ($eb -and $eb.Before) { $ex["BLK|$($x.B)"] = 1
            & $verdict 'explained' $what ("v{0} had ended its session at {1} ({2}, explained): no block of it there from then on" -f $sd.Hasnt, (T16 $eb.End.Time), $eb.End.Reason) }
        elseif ($eb) { & $verdict 'PENDING_ATTRIBUTION' $what ("v{0} ended its session only at {1} ({2}), after this block: the session was active in both builds here" -f $sd.Hasnt, (T16 $eb.End.Time), $eb.End.Reason) }
        else { & $verdict 'PENDING_ATTRIBUTION' $what 'its session is the same in both builds and alive in both at this bar' }
    }
    $dA = DiffKeys @($so.Arm | Where-Object { & $inR $_.Time }) @($sn.Arm | Where-Object { & $inR $_.Time }) 'Key'
    $armItems = @(@($dA.A | ForEach-Object { [pscustomobject]@{ X = $_; InOld = $true } }) + @($dA.B | ForEach-Object { [pscustomobject]@{ X = $_; InOld = $false } }))
    $explainedArmTimes = @()
    foreach ($it in $armItems) {
        $x = $it.X; $sd = & $side $x $it.InOld; $chainCount.ARM++
        $what = "ARM v$($sd.Has) only $($x.Key)"
        if (& $gate 'ARM' $x $sd $what "ARM|$($x.A)" "BLK|$($x.B)") { continue }
        $sessOf = $sd.HasS.BlkBy[$x.B].S
        $eb = & $endBefore $sd $sessOf $x.Time $false
        $dh = DirAt $sd.HasCtx $x.Time $true; $dn = DirAt $sd.NotCtx $x.Time $true
        if ($ex.ContainsKey("BLK|$($x.B)")) { $ex["ARM|$($x.A)"] = 1; $explainedArmTimes += $x.Time; & $verdict 'explained' $what 'its block exists in one build only, explained' }
        elseif ($eb -and $eb.Before) { $ex["ARM|$($x.A)"] = 1; $explainedArmTimes += $x.Time
            & $verdict 'explained' $what ("v{0} had ended the block's session at {1} ({2}, explained): nothing of it is ARMED there from then on" -f $sd.Hasnt, (T16 $eb.End.Time), $eb.End.Reason) }
        elseif ($dh -ne $dn) { $ex["ARM|$($x.A)"] = 1; $explainedArmTimes += $x.Time; & $verdict 'explained' $what "ARMED needs the H4 trend in the session's direction: v$($sd.Has) $dh, v$($sd.Hasnt) $dn" }
        elseif ($eb) { & $verdict 'PENDING_ATTRIBUTION' $what ("v{0} ended the block's session only at {1} ({2}), after this ARMED; same H4 direction in both" -f $sd.Hasnt, (T16 $eb.End.Time), $eb.End.Reason) }
        else { & $verdict 'PENDING_ATTRIBUTION' $what 'same block and session in both, same H4 direction' }
    }

    # models: a cycle lives from its ARMED bar to the next ARMED bar (Rule 15)
    $armsO = $so.ArmSorted; $armsN = $sn.ArmSorted
    $nextArm = { param($arms, [datetime]$t) foreach ($a in $arms) { if ($a.Time -gt $t) { return $a } }; return $null }
    $dM = DiffKeys @($so.Models | Where-Object { & $inR $_.Time }) @($sn.Models | Where-Object { & $inR $_.Time }) 'Key'
    foreach ($it in @(@($dM.A | ForEach-Object { [pscustomobject]@{ X = $_; InOld = $true } }) + @($dM.B | ForEach-Object { [pscustomobject]@{ X = $_; InOld = $false } }))) {
        $x = $it.X; $sd = & $side $x $it.InOld; $chainCount.MODEL++
        $what = "MODEL v$($sd.Has) only $($x.Row)"
        $a = CycleArm $sd.HasS $x                    # the gate checks the model lies inside this cycle
        if (& $gate 'MODEL' $x $sd $what '' $(if ($a) { "ARM|$($a.A)" } else { '' })) { continue }
        $armsMine = $(if ($it.InOld) { $armsO } else { $armsN }); $armsOther = $(if ($it.InOld) { $armsN } else { $armsO })
        if ($ex.ContainsKey("ARM|$($a.A)")) { & $verdict 'explained' $what ("its cycle (ARMED {0}) exists in one build only, explained, and the model lies inside it" -f (T16 $a.Time)); continue }
        $twin = @($armsOther | Where-Object { $_.A -eq $a.A }) | Select-Object -First 1
        if (-not $twin) { & $verdict 'PENDING_ATTRIBUTION' $what 'its ARMED differs between the builds and is not explained'; continue }
        $endMine = & $nextArm $armsMine $a.Time; $endOther = & $nextArm $armsOther $twin.Time
        $openMine = (-not $endMine) -or $x.Time -le $endMine.Time; $openOther = (-not $endOther) -or $x.Time -le $endOther.Time
        if ($openMine -and $openOther) { & $verdict 'UNEXPLAINED' $what 'same anchor, cycle open in both builds at this bar: the M5 data alone decides the model' }
        elseif (-not $openOther -and ($ex.ContainsKey("ARM|$($endOther.A)"))) { & $verdict 'explained' $what ("the other build closed this cycle at {0} with an ARMED that is itself explained" -f $endOther.Time.ToString('yyyy.MM.dd HH:mm')) }
        else { & $verdict 'PENDING_ATTRIBUTION' $what 'the cycle closes at different bars, and the closing ARMED is not explained' }
    }

    $chainN = ($chainCount.Values | Measure-Object -Sum).Sum
    Write-Host ("    chain differences in the common region: {0}" -f $(if ($chainN) { ($chainCount.Keys | Where-Object { $chainCount[$_] } | ForEach-Object { "$_ $($chainCount[$_])" }) -join '   ' } else { 'none' }))
    Write-Host ("    verdicts: explained {0}   PENDING_ATTRIBUTION {1}   UNEXPLAINED {2}" -f $tally.explained, $tally.PENDING_ATTRIBUTION, $tally.UNEXPLAINED) `
        -ForegroundColor $(if ($tally.UNEXPLAINED) { 'Red' } elseif ($tally.PENDING_ATTRIBUTION) { 'Yellow' } else { 'Gray' })
    $show = @($lines | Where-Object { $_ -notmatch '^explained' })
    $show | Select-Object -First 15 | ForEach-Object { Write-Host "      $_" -ForegroundColor $(if ($_ -match '^UNEXPLAINED') { 'Red' } else { 'Yellow' }) }
    if ($show.Count -gt 15) { Write-Host "      ... $($show.Count - 15) more in the file" -ForegroundColor Yellow }
    if ($lines.Count) {
        $out = Join-Path $dir ("attribution_" + ($Old.Src -replace '[^A-Za-z0-9]','_') + "__" + ($New.Src -replace '[^A-Za-z0-9]','_') + ".txt")
        $lines | Set-Content $out
        Write-Host "    every verdict with its reason written to $out" -ForegroundColor DarkGray
    }
    return [pscustomobject]@{ Unexplained = $tally.UNEXPLAINED; Pending = $tally.PENDING_ATTRIBUTION; Explained = $tally.explained; ModelDiff = $chainCount.MODEL }
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
    $pairs = 0; $cmp = 0; $pend = 0; $liveN = 0; $liveCtxN = 0; $strPend = 0; $bad = @(); $okRows = @(); $pendWhy = @(); $liqPend = 0
    for ($k = 1; $k -lt $sel.Count; $k++) {
        $A = $sel[$k - 1]; $B = $sel[$k]
        $rows = @($lv | Where-Object { $_.Idx -gt $A.EndIdx -and $_.Idx -lt $B.BeginIdx })
        $cs = $A.To.AddMinutes(10); $ce = $B.To
        if ($B.WarmEnd.AddMinutes(5) -gt $cs) { $cs = $B.WarmEnd.AddMinutes(5) }
        $bIn = @($B.Rows | Where-Object { $t = RowTime $_; $t -ge $cs -and $t -le $ce })
        # A-56: structure events. An H4 bar the live run consumed closed after
        # A's last M5 bar; B consumed it if it closed by B's last M5 bar.
        $lc  = @($liveCtx | Where-Object { $_.Src -eq $src -and $_.Idx -gt $A.EndIdx -and $_.Idx -lt $B.BeginIdx })
        $bc  = @((Get-Struct $B).Ctx | Where-Object { $_.Bar -gt $A.To -and $_.Bar -le $B.To })
        if ($rows.Count -eq 0 -and $bIn.Count -eq 0 -and $lc.Count -eq 0 -and $bc.Count -eq 0) { continue }
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
            $noId  = @(@($rows) + @($lc) | Where-Object { -not $_.Id }).Count
            $alien = @(@($rows) + @($lc) | Where-Object { $_.Id -and $_.Id -ne $A.Id }).Count
            if ($noId -or $alien) {
                $pend++
                $pendWhy += "build $($A.Build)->$($B.Build): live rows without run/init $noId, from another run/init than build $($A.Build) $alien"
                continue
            }
        }
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
        # A-55: what is left after the pending LIQ rows and the edge rows are
        # set aside is what this pair can prove. Nothing left = nothing compared.
        $lcIn = @($lc | Where-Object { $_.C.Bar -gt $A.To -and $_.C.Bar -le $B.To } | ForEach-Object { $_.C })
        if (($lIn.Count + $bIn.Count + $lcIn.Count + $bc.Count) -eq 0) {
            $pend++
            $pendWhy += "build $($A.Build)->$($B.Build): no judged event (LIQ pending or edge rows only) - not comparable"
            continue
        }
        $cmp++
        $liveN += $lIn.Count
        $okRows += $lIn
        foreach ($d in (DiffRows $lIn $bIn)) {
            $side = 'build only'; if ($d.Side -eq 'A only') { $side = 'live only' }
            $bad += [pscustomobject]@{ Side = $side; Row = $d.Row; Pair = "$($A.Build)->$($B.Build)" }
        }
        $liveCtxN += $lcIn.Count
        $dc  = DiffKeys $lcIn $bc 'KeyNoStr'
        $dcs = DiffKeys $lcIn $bc 'Key'
        foreach ($x in $dc.A) { $bad += [pscustomobject]@{ Side = 'live only';  Row = "CTX $($x.Key)"; Pair = "$($A.Build)->$($B.Build)" } }
        foreach ($x in $dc.B) { $bad += [pscustomobject]@{ Side = 'build only'; Row = "CTX $($x.Key)"; Pair = "$($A.Build)->$($B.Build)" } }
        $sn = $dcs.A.Count - $dc.A.Count
        if ($sn -gt 0) { $strPend += $sn; $pendWhy += "build $($A.Build)->$($B.Build): $sn H4 event(s) agree on swing and state but not on the strength number (the rebuild's H4 history starts later)" }
    }
    Write-Host ("  build pairs with a live stretch: {0}   comparable: {1}   pending review: {2}   liquidity pending: {3}" -f $pairs, $cmp, $pend, $liqPend)
    foreach ($w in $pendWhy) { Write-Host "    pending: $w" -ForegroundColor Yellow }
    if ($cmp -eq 0) { Write-Host "  nothing comparable yet - no PASS can be given." -ForegroundColor Yellow; return }
    Write-Host ("  live events compared: {0} (+ {1} H4 structure event(s))" -f $liveN, $liveCtxN)
    if ($okRows.Count) {
        $bm = $okRows | Group-Object { RowLabel $_ } | Sort-Object Name | ForEach-Object { "$($_.Name) $($_.Count)" }
        Write-Host ("  by model: " + ($bm -join '  |  '))
    }
    if ($bad.Count -eq 0) {
        $what = $(if ($liqPend -eq 0) { 'MODEL + LIQ' } else { "MODEL only; LIQ pending in $liqPend pair(s)" })
        Write-Host "  AGREE BOTH WAYS on every covered bar ($what)." -ForegroundColor $(if ($liqPend -eq 0 -and $strPend -eq 0) { 'Green' } else { 'Yellow' })
        if ($strPend -gt 0) { Write-Host "  $strPend H4 event(s) agree on swing and state but not on the strength number - PENDING REVIEW for those" -ForegroundColor Yellow }
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
        # A-57: with structure rows on both sides, every difference gets a verdict
        $hasCtx = ((Get-Struct $A).Ctx.Count -gt 0 -and (Get-Struct $B).Ctx.Count -gt 0)
        $att = $null
        if ($hasCtx) {
            $old = $A; $new = $B
            if ((VerNum $A.Ver) -gt (VerNum $B.Ver)) { $old = $B; $new = $A }
            $att = Show-StructAttribution $old $new $rs $re
            if ($moved) { Write-Host "    (windows start at different bars: an early difference can also come from the start - use a fixed window)" -ForegroundColor Yellow }
        }
        if ($att -and $att.Unexplained) {
            Write-Host ("  upgrade regression: {0} MODEL difference(s) over {1} / {2} row(s); {3} difference(s) UNEXPLAINED - not traced to the BOS de-dup" -f $d.Count, $mA.Count, $mB.Count, $att.Unexplained) -ForegroundColor Red
        } elseif ($att -and $att.Pending) {
            Write-Host ("  upgrade regression: {0} MODEL difference(s) over {1} / {2} row(s); {3} difference(s) PENDING_ATTRIBUTION - a manual conclusion is needed for each, so NOT 'all from the de-dup'" -f $d.Count, $mA.Count, $mB.Count, $att.Pending) -ForegroundColor Yellow
        } elseif ($att -and $att.Explained) {
            Write-Host ("  upgrade regression: {0} MODEL difference(s) over {1} / {2} row(s); all {3} difference(s) traced to the BOS de-dup with a concrete link" -f $d.Count, $mA.Count, $mB.Count, $att.Explained) -ForegroundColor Yellow
        } elseif ($d.Count) {
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

    # A-55: a verdict per category, and only over what was actually judged.
    # MODEL rows are always judged; LIQ rows only between two READY builds.
    # A WAITING build's LIQ rows are pending, so they cannot make up for an
    # empty MODEL sample - and no judged row at all is never a pass.
    $mmM = @($mm | Where-Object { (RowKind $_.Row) -eq 'MODEL' }).Count
    $mmL = @($mm | Where-Object { (RowKind $_.Row) -eq 'LIQ' }).Count
    $nM  = $mA.Count + $mB.Count
    $nL  = $(if ($liqCmp) { $lA.Count + $lB.Count } else { 0 })
    # A-56: H4 structure events, a judged category of their own
    $cA = @((Get-Struct $A).Ctx | Where-Object { $_.Bar -ge $rs -and $_.Bar -le $re })
    $cB = @((Get-Struct $B).Ctx | Where-Object { $_.Bar -ge $rs -and $_.Bar -le $re })
    # A different event, swing or state is a MISMATCH. The same event with only
    # str (the leg's BOS count) numbered differently is not: str counts from
    # where the H4 history lets the leg begin, so two builds whose H4 windows
    # start at different bars can number a leg that began before the later
    # start differently. That is PENDING REVIEW - neither a pass nor a repaint.
    $dC  = DiffKeys $cA $cB 'KeyNoStr'
    $dCs = DiffKeys $cA $cB 'Key'
    $mmC = $dC.A.Count + $dC.B.Count
    $strC = $dCs.A.Count - $dC.A.Count
    $nC  = $cA.Count + $cB.Count
    foreach ($x in $dC.A) { $cls += [pscustomobject]@{ Class = 'MISMATCH'; Side = 'A only'; Time = $x.Bar; Row = "CTX $($x.Key)" } }
    foreach ($x in $dC.B) { $cls += [pscustomobject]@{ Class = 'MISMATCH'; Side = 'B only'; Time = $x.Bar; Row = "CTX $($x.Key)" } }
    $mm = @($cls | Where-Object Class -eq 'MISMATCH')
    $vC = $(if ($mmC) { "MISMATCH ($mmC)" } elseif ($nC -eq 0) { 'no event on either side (nothing judged)' }
            elseif ($strC) { "same events, strength numbered differently on $strC - PENDING REVIEW" }
            else { "IDENTICAL over $($cA.Count) / $($cB.Count) event(s)" })
    $vM  = $(if ($mmM) { "MISMATCH ($mmM)" } elseif ($nM -eq 0) { 'INSUFFICIENT SAMPLE - no MODEL row on either side' } else { "IDENTICAL over $($mA.Count) / $($mB.Count) row(s)" })
    $vL  = $(if (-not $liqCmp) { 'PENDING - liquidity history WAITING in one build, LIQ rows not judged' }
             elseif ($mmL) { "MISMATCH ($mmL)" } elseif ($nL -eq 0) { 'no event on either side (nothing judged)' }
             else { "IDENTICAL over $($lA.Count) / $($lB.Count) row(s)" })
    Write-Host "    MODEL  $vM" -ForegroundColor $(if ($mmM) { 'Red' } elseif ($nM -eq 0) { 'Yellow' } else { 'Gray' })
    Write-Host "    LIQ    $vL" -ForegroundColor $(if ($mmL) { 'Red' } elseif (-not $liqCmp -or $nL -eq 0) { 'Yellow' } else { 'Gray' })
    Write-Host "    CTX    $vC" -ForegroundColor $(if ($mmC) { 'Red' } elseif ($nC -eq 0 -or $strC) { 'Yellow' } else { 'Gray' })

    if ($mm.Count -gt 0) {
        Write-Host "  $($mm.Count) event(s) differ INSIDE the comparable region - repaint or non-determinism:" -ForegroundColor Red
        $mm | Select-Object -First 20 | ForEach-Object { Write-Host ("    {0}  {1}" -f $_.Side, $_.Row) }
    } elseif (($nM + $nL + $nC) -eq 0) {
        Write-Host "  INSUFFICIENT SAMPLE - no judged event inside the comparable region; nothing was compared." -ForegroundColor Yellow
    } elseif ($pend.Count -gt 0 -or -not $known -or $A.WarmEst -or $B.WarmEst -or $strC) {
        Write-Host "  no difference inside the comparable region - PENDING REVIEW, not a pass:" -ForegroundColor Yellow
        if ($strC)                  { Write-Host "    $strC H4 event(s) with the same swing and state but another strength number (H4 history start)" -ForegroundColor Yellow }
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
