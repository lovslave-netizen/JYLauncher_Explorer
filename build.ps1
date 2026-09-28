# 빌드 스크립트: exe 2개(dist\JYTools) → 설치 파일(dist_installer\JYTools-Setup-버전.exe) + sha256
#   사용:  .\build.ps1            (exe 만)
#          .\build.ps1 -Installer (Inno Setup 도 있으면 설치 파일까지)
param([switch]$Installer)
$ErrorActionPreference = "Continue"   # PyInstaller 는 진행 로그를 stderr 로 내보내서 Stop 이면 오류로 오인됨
Set-Location $PSScriptRoot

$version = (python -c "from version import __version__ as v; print(v)").Trim()
Write-Host "버전 $version 빌드"

python -m PyInstaller --noconfirm --clean JYTools.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 실패" }

if ($Installer) {
    $iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
              "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) { throw "Inno Setup 6 (ISCC.exe) 를 찾을 수 없음" }
    & $iscc "/DAppVersion=$version" installer\JYTools.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup 실패" }
    $setup = "dist_installer\JYTools-Setup-$version.exe"
    $hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
    "$hash  JYTools-Setup-$version.exe" | Set-Content "$setup.sha256" -Encoding ascii
    Write-Host "설치 파일: $setup"
    Write-Host "sha256: $hash"
}
