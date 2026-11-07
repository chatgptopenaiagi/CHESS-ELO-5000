#requires -Version 7.0
[CmdletBinding()]
param([string]$PackagePath)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if(-not$PackagePath){$PackagePath=Join-Path $root 'dist\CHESS-ELO-5000-Joomla-Package.zip'}
Add-Type -AssemblyName System.IO.Compression
$checked=[Collections.Generic.List[string]]::new()
function Assert-Entry([IO.Compression.ZipArchive]$Zip,[string]$Path,[bool]$Folder){
    $Path=$Path.Replace('\','/').Trim('/')
    $found=if($Folder){@($Zip.Entries|Where-Object{$_.FullName.StartsWith($Path+'/')-and-not$_.FullName.EndsWith('/')}).Count-gt0}else{$null-ne$Zip.GetEntry($Path)}
    if(-not$found){throw "Joomla manifest declares missing file/folder with no real files: $Path"}
    $checked.Add($Path)
}
function Read-ZipXml([IO.Compression.ZipArchive]$Zip,[string]$Path){$entry=$Zip.GetEntry($Path);if(-not$entry){throw "Manifest missing: $Path"};$reader=[IO.StreamReader]::new($entry.Open());try{return [xml]$reader.ReadToEnd()}finally{$reader.Dispose()}}
$outer=[IO.Compression.ZipFile]::OpenRead($PackagePath)
try{
    $manifest=Read-ZipXml $outer 'pkg_chesselo5000.xml'
    foreach($child in $manifest.extension.files.file){
        $path=[string]$manifest.extension.files.folder+'/'+$child.InnerText
        Assert-Entry $outer $path $false
        $entry=$outer.GetEntry($path);$memory=[IO.MemoryStream]::new();$entryStream=$entry.Open()
        try{$entryStream.CopyTo($memory)}finally{$entryStream.Dispose()}
        $memory.Position=0;$nested=[IO.Compression.ZipArchive]::new($memory,[IO.Compression.ZipArchiveMode]::Read)
        try{
            $xml=Read-ZipXml $nested $(if($child.type-eq'component'){'chesselo5000.xml'}else{'templateDetails.xml'})
            if($child.type-eq'component'){
                foreach($group in @($xml.extension.files,$xml.extension.media,$xml.extension.administration.files)){
                    $prefix=$group.GetAttribute('folder')
                    foreach($file in $group.SelectNodes('filename')){Assert-Entry $nested ($prefix+'/'+$file.InnerText) $false}
                    foreach($folder in $group.SelectNodes('folder')){Assert-Entry $nested ($prefix+'/'+$folder.InnerText) $true}
                }
            }else{
                foreach($file in $xml.extension.files.filename){Assert-Entry $nested ([string]$file) $false}
                foreach($folder in $xml.extension.files.folder){Assert-Entry $nested ([string]$folder) $true}
            }
        }finally{$nested.Dispose();$memory.Dispose()}
    }
}finally{$outer.Dispose()}
$receipt=[ordered]@{checked_utc=[DateTime]::UtcNow.ToString('o');status='PASS';artifact=$PackagePath;sha256=(Get-FileHash -LiteralPath $PackagePath -Algorithm SHA256).Hash;manifest_entries_checked=$checked.Count;entries=$checked;scope='Every declared component/template file exists; declared folders contain real files, including after nested ZIP extraction'}
$evidence=Join-Path $root 'evidence\joomla';New-Item -ItemType Directory -Path $evidence -Force|Out-Null
$receipt|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $evidence 'package-content-verification.json') -Encoding utf8
[pscustomobject]$receipt
