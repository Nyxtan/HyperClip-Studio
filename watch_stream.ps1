param(
    [Parameter(Mandatory = $true)]
    [string]$Url,
    [int]$MaxSeconds = 300,
    [int]$Chunk = 90,
    [int]$ClipLen = 30,
    [int]$LeadIn = 6,
    [int]$Top = 1,
    [string]$MomentSource = "chat",
    [string]$Quality = "max",
    [string]$OutputDir = "output",
    [int]$Loops = 0,
    [int]$SleepSeconds = 10
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $repo 'run.ps1'
$ytKey = [Environment]::GetEnvironmentVariable('YOUTUBE_API_KEY', 'User')
if (-not $ytKey) { $ytKey = [Environment]::GetEnvironmentVariable('YOUTUBE_API_KEY', 'Process') }
if ($ytKey) { $env:YOUTUBE_API_KEY = $ytKey }

if ($Loops -le 0) {
    Write-Host "Continuous live monitor (py-autovod-style). Press Ctrl+C to stop."
} else {
    Write-Host "Running $Loops capture loop(s)."
}

$i = 0
while ($true) {
    $i++
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Write-Host "`n=== [$stamp] Capture loop #$i ==="
    try {
        & powershell -ExecutionPolicy Bypass -File $runner clip.py $Url --gameplay-confirmed --max-seconds $MaxSeconds --chunk $Chunk --clip-len $ClipLen --lead-in $LeadIn --top $Top --moment-source $MomentSource --quality $Quality --output-dir $OutputDir
    } catch {
        Write-Warning "Loop #$i failed: $($_.Exception.Message)"
    }
    if ($Loops -gt 0 -and $i -ge $Loops) { break }
    Write-Host "Sleeping $SleepSeconds s before next check..."
    Start-Sleep -Seconds $SleepSeconds
}
