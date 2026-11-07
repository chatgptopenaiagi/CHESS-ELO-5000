#requires -Version 7.0
[CmdletBinding()]
param([string]$PythonPath,[switch]$Development)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if(-not $PythonPath){
    $registry=Join-Path $env:USERPROFILE '.codex\machine-capabilities\software-capabilities.json'
    if(Test-Path -LiteralPath $registry){
        $inventory=Get-Content -LiteralPath $registry -Raw|ConvertFrom-Json
        $candidate=$inventory.software|Where-Object { $_.name -like 'Python environment:*' -and $_.verification_status -eq 'VERIFIED FUNCTIONAL' -and $_.executable_path -notlike '*-32*' -and (Test-Path -LiteralPath $_.executable_path -PathType Leaf) }|Sort-Object @{Expression={if($_.name -like '*anaconda3*'){0}else{1}}}|Select-Object -First 1
        if($candidate){$PythonPath=$candidate.executable_path}
    }
    if(-not $PythonPath){$command=Get-Command python.exe -ErrorAction SilentlyContinue;if($command){$PythonPath=$command.Source}}
}
if(-not $PythonPath -or -not(Test-Path -LiteralPath $PythonPath)){throw 'A working Python3.11+ is required. Supply -PythonPath with its executable.'}
& $PythonPath -c 'import sys; assert (3,11) <= sys.version_info < (3,16), "Python3.11 through3.15 required; tested on3.14"'
if($LASTEXITCODE -ne 0){throw 'Python version check failed'}
$python=Join-Path $root '.venv\Scripts\python.exe'
if(-not(Test-Path -LiteralPath $python)){
    & $PythonPath -m venv (Join-Path $root '.venv')
    if($LASTEXITCODE -ne 0){throw 'Virtual environment creation failed'}
}
$requirements=if(Test-Path -LiteralPath (Join-Path $root 'requirements-lock.txt')){Join-Path $root 'requirements-lock.txt'}else{Join-Path $root 'requirements.txt'}
if(Test-Path -LiteralPath (Join-Path $root 'wheelhouse')){& $python -m pip install --no-index --find-links (Join-Path $root 'wheelhouse') -r $requirements}else{& $python -m pip install -r $requirements}
if($LASTEXITCODE -ne 0){throw 'Chess dependency installation failed'}
if($Development){& $python -m pip install 'pytest==9.1.1';if($LASTEXITCODE -ne 0){throw 'Test dependency installation failed'}}
# The launcher binds this complete source tree through PYTHONPATH. No editable
# installation points at another checkout and no build tool is required to play.
[pscustomobject]@{Python=$python;Status='Installed';Product='CHESS ELO 5000'}
