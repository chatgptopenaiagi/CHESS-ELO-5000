#requires -Version 7.0
[CmdletBinding()]
param([switch]$Standalone)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if($Standalone){$url='http://127.0.0.1:18961'}else{$url='http://127.0.0.1:18952'}
Start-Process $url
Write-Output $url
