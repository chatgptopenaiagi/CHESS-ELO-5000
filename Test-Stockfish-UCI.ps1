#requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateRange(1,40)][int]$Depth = 20,
    [ValidateRange(10,600)][int]$TimeoutSeconds = 180,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'evidence')
)
$ErrorActionPreference = 'Stop'
$engine = Join-Path $PSScriptRoot 'stockfish\stockfish\stockfish-windows-x86-64-universal.exe'
if (-not (Test-Path -LiteralPath $engine -PathType Leaf)) { throw "Engine missing: $engine" }
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$logPath = Join-Path $OutputDirectory "uci-$stamp.log"
$receiptPath = Join-Path $OutputDirectory "uci-$stamp.json"
$log = [System.Collections.Generic.List[string]]::new()
$settings = [ordered]@{Threads=6; Hash=512; MultiPV=3; 'Skill Level'=20; UCI_LimitStrength='false'}
$info = [Diagnostics.ProcessStartInfo]::new($engine)
$info.UseShellExecute = $false
$info.CreateNoWindow = $true
$info.RedirectStandardInput = $true
$info.RedirectStandardOutput = $true
$info.RedirectStandardError = $true
$info.WorkingDirectory = Split-Path -Parent $engine
$process = [Diagnostics.Process]::new()
$process.StartInfo = $info
$timer = [Diagnostics.Stopwatch]::StartNew()
$result = [ordered]@{ started_utc=[DateTime]::UtcNow.ToString('o'); engine=$engine; sha256=(Get-FileHash -LiteralPath $engine -Algorithm SHA256).Hash; settings=$settings; depth=$Depth; timeout_seconds=$TimeoutSeconds; status='FAIL'; log=$logPath }
function Send-Uci([string]$Command) {
    $log.Add(('> ' + $Command))
    $process.StandardInput.WriteLine($Command)
    $process.StandardInput.Flush()
}
function Read-Until([string]$Pattern) {
    while ($true) {
        $remaining = $TimeoutSeconds * 1000 - $timer.ElapsedMilliseconds
        if ($remaining -le 0) { throw "UCI deadline exceeded while awaiting $Pattern" }
        $read = $process.StandardOutput.ReadLineAsync()
        if (-not $read.Wait([int][Math]::Min($remaining, [int]::MaxValue))) { throw "UCI deadline exceeded while awaiting $Pattern" }
        $line = $read.Result
        if ($null -eq $line) { throw "Engine output closed while awaiting $Pattern" }
        $log.Add(('< ' + $line))
        if ($line -match $Pattern) { return $line }
    }
}
try {
    if (-not $process.Start()) { throw 'Engine process did not start' }
    $result.pid = $process.Id
    $stderrTask = $process.StandardError.ReadToEndAsync()
    Send-Uci 'uci'
    $null = Read-Until '^uciok$'
    $result.identity = @($log | Where-Object { $_ -match '^< id ' })
    $result.options = @($log | Where-Object { $_ -match '^< option ' })
    if (-not ($result.identity -match 'id name Stockfish 19$')) { throw 'Expected Stockfish 19 identity was not returned' }
    foreach ($item in $settings.GetEnumerator()) { Send-Uci "setoption name $($item.Key) value $($item.Value)" }
    Send-Uci 'isready'
    $result.readyok = Read-Until '^readyok$'
    Send-Uci 'ucinewgame'
    Send-Uci 'position startpos'
    Send-Uci "go depth $Depth"
    $bestmove = Read-Until '^bestmove '
    if ($bestmove -notmatch '^bestmove ([a-h][1-8][a-h][1-8][qrbn]?)(?: ponder ([a-h][1-8][a-h][1-8][qrbn]?))?$') { throw "Invalid bestmove: $bestmove" }
    $result.bestmove = $bestmove
    $result.final_depth_lines = @($log | Where-Object { $_ -match "^< info depth $Depth " })
    if ($result.final_depth_lines.Count -lt 3) { throw 'Expected three MultiPV lines at requested depth' }
    Send-Uci 'quit'
    if (-not $process.WaitForExit(5000)) { throw 'Engine did not exit after quit' }
    $result.exit_code = $process.ExitCode
    $result.stderr = $stderrTask.GetAwaiter().GetResult()
    if ($process.ExitCode -ne 0) { throw "Engine exit code $($process.ExitCode)" }
    $result.status = 'PASS'
} catch {
    $result.error = $_.Exception.Message
    throw
} finally {
    if ($process.Id -and -not $process.HasExited) { $process.Kill(); $process.WaitForExit() }
    $result.elapsed_seconds = [Math]::Round($timer.Elapsed.TotalSeconds,3)
    $result.finished_utc = [DateTime]::UtcNow.ToString('o')
    $log | Set-Content -LiteralPath $logPath -Encoding utf8
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receiptPath -Encoding utf8
    $process.Dispose()
}
$result | ConvertTo-Json -Depth 8
