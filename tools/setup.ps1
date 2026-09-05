$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
    }
    & .venv/Scripts/python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'dependency installation failed' }
    New-Item -ItemType Directory -Force -Path .tools | Out-Null
    $signerPath = '.tools/uber-apk-signer-1.3.0.jar'
    if (-not (Test-Path -LiteralPath $signerPath)) {
        Invoke-WebRequest -UseBasicParsing 'https://github.com/patrickfav/uber-apk-signer/releases/download/v1.3.0/uber-apk-signer-1.3.0.jar' -OutFile $signerPath
    }
    $expectedHash = 'E1299FD6FCF4DA527DD53735B56127E8EA922A321128123B9C32D619BBA1D835'
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $signerPath).Hash -ne $expectedHash) {
        throw 'APK signer checksum mismatch'
    }
    Write-Output 'Local runtime ready. JDK java and keytool are also required to sign a client.'
} finally {
    Pop-Location
}
