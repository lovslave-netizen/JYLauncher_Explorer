# CI: run one test script; on failure, emit the last lines of its output as a GitHub annotation (::error)
#   usage: ./ci_test.ps1 test_smoke.py
param([Parameter(Mandatory = $true)][string]$Script)
$out = python $Script 2>&1 | Out-String
Write-Host $out
if ($LASTEXITCODE -ne 0) {
    $tail = (($out -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -Last 14) -join "%0A"
    Write-Host "::error title=$Script failed::$tail"
    exit 1
}
