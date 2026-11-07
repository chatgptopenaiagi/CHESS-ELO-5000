#requires -Version 7.0
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$config=Get-Content -LiteralPath (Join-Path $root 'runtime\joomla\services.json') -Raw|ConvertFrom-Json
if($config.product -ne 'CHESS-ELO-5000'){throw 'Invalid chess service identity.'}
$owned=@(Get-CimInstance Win32_Process|Where-Object{$_.ExecutablePath-eq$config.apache_exe -and $_.CommandLine-like"*$($config.apache_config)*"})
foreach($p in $owned){Stop-Process -Id $p.ProcessId -ErrorAction SilentlyContinue}
$listener=Get-NetTCPConnection -State Listen -LocalPort $config.database_port -ErrorAction SilentlyContinue|Select-Object -First 1
if($listener){
    $process=Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    if($process.ExecutablePath-ne$config.mysql_exe -or $process.CommandLine-notlike"*$($config.mysql_config)*"){throw 'Database port ownership mismatch; no database stop attempted.'}
    $private=Join-Path $root 'runtime\private';$access=Get-Content -LiteralPath (Join-Path $private 'joomla-access.json') -Raw|ConvertFrom-Json
    $defaults=Join-Path $private 'joomla-shutdown.cnf'
    try{
        "[client]`nuser=root`npassword=$($access.database_root_password)`nhost=127.0.0.1`nport=$($config.database_port)`nprotocol=tcp"|Set-Content -LiteralPath $defaults -Encoding ascii
        & 'C:\xampp\mysql\bin\mysqladmin.exe' "--defaults-extra-file=$defaults" shutdown
        if($LASTEXITCODE-ne0){throw 'Graceful chess database shutdown failed; process preserved.'}
    }finally{if(Test-Path -LiteralPath $defaults){Remove-Item -LiteralPath $defaults}}
}
[pscustomobject]@{product=$config.product;status='Stopped only process identities bound to the chess configuration files'}
