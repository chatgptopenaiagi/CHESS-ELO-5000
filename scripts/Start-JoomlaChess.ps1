#requires -Version 7.0
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$state=Join-Path $root 'runtime\joomla'
$configPath=Join-Path $state 'services.json'
if(-not(Test-Path -LiteralPath $configPath)){throw 'Run Install-JoomlaChess.ps1 first.'}
$config=Get-Content -LiteralPath $configPath -Raw|ConvertFrom-Json
if($config.product -ne 'CHESS-ELO-5000'){throw 'Invalid chess service identity.'}
function Start-Owned([string]$Name,[string]$Exe,[string]$Config,[int]$Port,[string[]]$Arguments){
    $listener=Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue|Select-Object -First 1
    if($listener){
        $current=Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        if($current.ExecutablePath -ne $Exe -or $current.CommandLine -notlike "*$Config*"){throw "Port $Port belongs to a different process."}
        return [pscustomobject]@{name=$Name;pid=$listener.OwningProcess;reused=$true;port=$Port}
    }
    $p=Start-Process -FilePath $Exe -ArgumentList $Arguments -WorkingDirectory (Split-Path -Parent $Exe) -WindowStyle Hidden -PassThru
    $deadline=[DateTime]::UtcNow.AddSeconds(30)
    do{
        Start-Sleep -Milliseconds 250
        if($p.HasExited){throw "$Name exited with code $($p.ExitCode). Read chess runtime logs."}
        $ready=Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue|Select-Object -First 1
    }until($ready -or [DateTime]::UtcNow-ge$deadline)
    if(-not$ready){throw "$Name failed to listen on port $Port within 30 seconds."}
    [pscustomobject]@{name=$Name;pid=$p.Id;reused=$false;port=$Port}
}
$db=Start-Owned 'Chess MariaDB' $config.mysql_exe $config.mysql_config $config.database_port @("--defaults-file=`"$($config.mysql_config)`"",'--console')
$web=Start-Owned 'Chess Apache' $config.apache_exe $config.apache_config $config.web_port @('-f',"`"$($config.apache_config)`"")
[pscustomobject]@{product=$config.product;url=$config.site_url;database=$db;web=$web}
