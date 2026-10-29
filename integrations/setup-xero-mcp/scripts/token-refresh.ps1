$ErrorActionPreference = 'Stop'
& py -3 (Join-Path $PSScriptRoot 'xero_auth.py') serve
exit $LASTEXITCODE
