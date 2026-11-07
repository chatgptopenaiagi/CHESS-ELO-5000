#requires -Version 7.0
[CmdletBinding()]
param([string]$OutputDirectory)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if(-not$OutputDirectory){$OutputDirectory=Join-Path $root 'dist'}
$stage=Join-Path $root ('runtime\joomla\package-stage-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $OutputDirectory,(Join-Path $stage 'component'),(Join-Path $stage 'template'),(Join-Path $stage 'package\packages') -Force|Out-Null
function Copy-Tree([string]$Source,[string]$Destination){Get-ChildItem -LiteralPath $Source -Force|ForEach-Object{Copy-Item -LiteralPath $_.FullName -Destination $Destination -Recurse -Force}}
Copy-Tree (Join-Path $root 'joomla\component') (Join-Path $stage 'component')
$media=Join-Path $stage 'component\media'
New-Item -ItemType Directory -Path $media -Force|Out-Null
foreach($file in @('index.html','app.js','style.css')){
    $source=Join-Path $root "client\web\$file"
    if(-not(Test-Path -LiteralPath $source -PathType Leaf)){throw "Client source missing: $source"}
    Copy-Item -LiteralPath $source -Destination (Join-Path $media $file) -Force
}
Copy-Tree (Join-Path $root 'joomla\template') (Join-Path $stage 'template')
Copy-Tree (Join-Path $root 'joomla\package') (Join-Path $stage 'package')
function Zip-Tree([string]$Source,[string]$Output){
    Add-Type -AssemblyName System.IO.Compression
    $stream=[IO.File]::Open($Output,[IO.FileMode]::Create)
    $zip=[IO.Compression.ZipArchive]::new($stream,[IO.Compression.ZipArchiveMode]::Create)
    $fixedTime=[DateTimeOffset]::new(1980,1,1,0,0,0,[TimeSpan]::Zero)
    [string[]]$paths=@(Get-ChildItem -LiteralPath $Source -Recurse -Force|ForEach-Object{[IO.Path]::GetRelativePath($Source,$_.FullName).Replace('\','/')})
    [Array]::Sort($paths,[StringComparer]::Ordinal)
    try{
        foreach($relative in $paths){
            $item=Get-Item -LiteralPath (Join-Path $Source $relative)
            if($item.PSIsContainer){$entry=$zip.CreateEntry($relative+'/');$entry.ExternalAttributes=16;$entry.LastWriteTime=$fixedTime}
            else{
                $entry=$zip.CreateEntry($relative,[IO.Compression.CompressionLevel]::Optimal)
                $entry.ExternalAttributes=0;$entry.LastWriteTime=$fixedTime
                $inputFile=[IO.File]::OpenRead($item.FullName);$entryStream=$entry.Open()
                try{$inputFile.CopyTo($entryStream)}finally{$entryStream.Dispose();$inputFile.Dispose()}
            }
        }
    }finally{$zip.Dispose();$stream.Dispose()}
}
Zip-Tree (Join-Path $stage 'component') (Join-Path $stage 'package\packages\com_chesselo5000.zip')
Zip-Tree (Join-Path $stage 'template') (Join-Path $stage 'package\packages\tpl_chesslab.zip')
$output=Join-Path $OutputDirectory 'CHESS-ELO-5000-Joomla-Package.zip'
Zip-Tree (Join-Path $stage 'package') $output
& (Join-Path $PSScriptRoot 'Test-JoomlaChessPackage.ps1') -PackagePath $output | Out-Null
[ordered]@{created_utc=[DateTime]::UtcNow.ToString('o');artifact=$output;sha256=(Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash;inputs=@(Get-ChildItem -LiteralPath (Join-Path $root 'joomla'),(Join-Path $root 'client\web') -File -Recurse|ForEach-Object{[ordered]@{path=[IO.Path]::GetRelativePath($root,$_.FullName).Replace('\','/');sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash}})}|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $root 'evidence\joomla\package-manifest.json') -Encoding utf8
[pscustomobject]@{file=$output;bytes=(Get-Item -LiteralPath $output).Length;sha256=(Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash}
