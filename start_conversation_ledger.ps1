param(
    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-EnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Default
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $Default
    }

    foreach ($rawLine in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            continue
        }
        $parts = $line.Split("=", 2)
        if ($parts[0].Trim() -eq $Key) {
            $value = $parts[1].Trim()
            if ($value) {
                return $value
            }
        }
    }

    return $Default
}

function Test-TcpPortOpen {
    param(
        [string]$Host,
        [int]$Port
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($Host, $Port, $null, $null)
        $connected = $async.AsyncWaitHandle.WaitOne(400)
        if (-not $connected) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Start-LedgerProcess {
    param(
        [string]$RepoRoot,
        [string]$WindowTitle,
        [string]$Command
    )

    $escapedRoot = $RepoRoot.Replace("'", "''")
    $escapedTitle = $WindowTitle.Replace("'", "''")
    $script = @"
`$Host.UI.RawUI.WindowTitle = '$escapedTitle'
Set-Location -LiteralPath '$escapedRoot'
python -m conversation_ledger $Command
"@

    Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoExit",
        "-Command",
        $script
    ) | Out-Null
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$envPath = Join-Path $repoRoot ".env"

$collectorHost = Get-EnvValue -Path $envPath -Key "COLLECTOR_HOST" -Default "127.0.0.1"
$collectorPort = [int](Get-EnvValue -Path $envPath -Key "COLLECTOR_PORT" -Default "8765")
$shellHost = Get-EnvValue -Path $envPath -Key "SHELL_HOST" -Default "127.0.0.1"
$shellPort = [int](Get-EnvValue -Path $envPath -Key "SHELL_PORT" -Default "8766")

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "python was not found in PATH."
}

if (-not (Test-TcpPortOpen -Host $collectorHost -Port $collectorPort)) {
    Start-LedgerProcess -RepoRoot $repoRoot -WindowTitle "ConversationLedger Collector" -Command "run-collector"
    Start-Sleep -Seconds 1
}

if (-not (Test-TcpPortOpen -Host $shellHost -Port $shellPort)) {
    Start-LedgerProcess -RepoRoot $repoRoot -WindowTitle "ConversationLedger Shell" -Command "run-shell"
    Start-Sleep -Seconds 1
}

$shellUrl = "http://{0}:{1}/" -f $shellHost, $shellPort
if (-not $NoBrowser) {
    Start-Process $shellUrl | Out-Null
}

Write-Host ("Collector: http://{0}:{1}/health" -f $collectorHost, $collectorPort)
Write-Host ("Shell: {0}" -f $shellUrl)
