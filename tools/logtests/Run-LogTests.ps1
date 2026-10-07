# ============================================================
#  Parser regression for ReloadTest.ps1 (v2.51, A-48 / A-51 / A-52)
#
#  Every folder here holds one synthetic MT5 log; cases.json says which
#  ReloadTest arguments to run on it, which lines MUST appear in the output
#  and which must NOT (a forbidden "IDENTICAL" on a damaged log is the
#  failure this guards against). The attribution_*.txt a version comparison
#  writes (one verdict per line) is read as part of the output. Needs
#  PowerShell only:
#
#     pwsh -File .\Run-LogTests.ps1                       the ReloadTest.ps1 one folder up
#     pwsh -File .\Run-LogTests.ps1 -Script <path>        any other copy (e.g. v2.50, as a control)
#
#  Synthetic logs test the parser, not the indicator: a pass here is not an
#  MT5 replay, a compile or a repaint test.
# ============================================================
param([string]$Script = (Join-Path $PSScriptRoot '..\ReloadTest.ps1'))
$Script = (Resolve-Path $Script).Path
$exe    = (Get-Process -Id $PID).Path               # this PowerShell, whichever it is
$cases  = Get-Content (Join-Path $PSScriptRoot 'cases.json') -Raw | ConvertFrom-Json
$ok = 0; $n = 0; $bad = @()
foreach ($p in $cases.PSObject.Properties) {
    $n++; $c = $p.Value
    Push-Location (Join-Path $PSScriptRoot $p.Name)
    Remove-Item 'attribution_*.txt' -ErrorAction SilentlyContinue      # (A-58) the per-verdict file is checked too:
    $out = (& $exe -NoProfile -File $Script @($c.args) 2>&1 | Out-String)   # never one left by an earlier run
    foreach ($f in @(Get-ChildItem 'attribution_*.txt' -ErrorAction SilentlyContinue)) { $out += "`n" + (Get-Content $f.FullName -Raw) }
    Pop-Location
    $miss = @($c.expect | Where-Object { -not $out.Contains($_) })
    $hit  = @($c.forbid | Where-Object { $out.Contains($_) })
    if ($miss.Count -eq 0 -and $hit.Count -eq 0) { $ok++; Write-Host ("PASS  {0}" -f $p.Name) -ForegroundColor Green }
    else { Write-Host ("FAIL  {0}" -f $p.Name) -ForegroundColor Red; $bad += [pscustomobject]@{ Name = $p.Name; Miss = $miss; Hit = $hit } }
}
Write-Host ("`n{0}/{1} cases as expected" -f $ok, $n) -ForegroundColor $(if ($ok -eq $n) { 'Green' } else { 'Red' })
foreach ($b in $bad) {
    if ($b.Miss.Count) { Write-Host "  $($b.Name) missing:   $($b.Miss -join ' | ')" -ForegroundColor Red }
    if ($b.Hit.Count)  { Write-Host "  $($b.Name) forbidden: $($b.Hit -join ' | ')" -ForegroundColor Red }
}
