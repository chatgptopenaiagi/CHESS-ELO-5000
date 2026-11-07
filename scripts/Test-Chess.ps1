#requires -Version 7.0
[CmdletBinding()]
param()
$root=Split-Path -Parent $PSScriptRoot
Push-Location $root
try{
    & (Join-Path $root '.venv\Scripts\python.exe') -m pytest tests -q --junitxml=evidence/test-results.xml
    if($LASTEXITCODE-ne0){throw 'Chess regression tests failed'}
    $node=Get-Command node.exe -ErrorAction SilentlyContinue
    if($node -and (Test-Path -LiteralPath (Join-Path $root 'tests\web_contract.test.cjs'))){& $node.Source --test tests/web_contract.test.cjs;if($LASTEXITCODE-ne0){throw 'Client tests failed'}}
}finally{Pop-Location}
