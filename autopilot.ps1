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
    [string]$Layout = "circle",
    [string]$Font = "beast",
    [string]$RingColor = "auto",
    [string]$OutputDir = "output",
    [switch]$AutoPost
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $repo 'run.ps1'

# Load user environment variables or prompt interactively if missing
if (-not $env:GEMINI_API_KEY) {
    $userGemini = [Environment]::GetEnvironmentVariable('GEMINI_API_KEY', 'User')
    if ($userGemini) {
        $env:GEMINI_API_KEY = $userGemini
    } else {
        $inputKey = Read-Host "Enter your Google Gemini API Key (press Enter to skip/use default template)"
        if ($inputKey.Trim()) {
            $env:GEMINI_API_KEY = $inputKey.Trim()
            [Environment]::SetEnvironmentVariable('GEMINI_API_KEY', $inputKey.Trim(), 'User')
        }
    }
}
$env:YOUTUBE_API_KEY = [Environment]::GetEnvironmentVariable('YOUTUBE_API_KEY', 'User')
$env:ZERNIO_API_KEY = [Environment]::GetEnvironmentVariable('ZERNIO_API_KEY', 'User')
$env:ZERNIO_YOUTUBE_ACCOUNT_ID = [Environment]::GetEnvironmentVariable('ZERNIO_YOUTUBE_ACCOUNT_ID', 'User')
$env:ZERNIO_INSTAGRAM_ACCOUNT_ID = [Environment]::GetEnvironmentVariable('ZERNIO_INSTAGRAM_ACCOUNT_ID', 'User')
$env:GTA_UNATTENDED_POSTS = "1"

Write-Host "=========================================================="
Write-Host " REAL-TIME AUTO-PILOT CLIPPER & POSTER (YouTube + Instagram)"
Write-Host " URL: $Url"
Write-Host " Auto-Post Enabled: $($AutoPost.IsPresent)"
Write-Host " Press Ctrl+C to stop."
Write-Host "==========================================================`n"

$i = 0
while ($true) {
    $i++
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Write-Host "`n=== [$stamp] Capture loop #$i ==="

    # Record existing clips before this loop
    $beforeClips = @(Get-ChildItem -Path $OutputDir -Filter "gta-*.json" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)

    try {
        & powershell -ExecutionPolicy Bypass -File $runner clip.py $Url --gameplay-confirmed --max-seconds $MaxSeconds --chunk $Chunk --clip-len $ClipLen --lead-in $LeadIn --top $Top --moment-source $MomentSource --quality $Quality --layout $Layout --font $Font --ring-color $RingColor --output-dir $OutputDir
    } catch {
        Write-Warning "Loop #$i failed: $($_.Exception.Message)"
    }

    # Identify new clips generated in this loop
    $afterClips = @(Get-ChildItem -Path $OutputDir -Filter "gta-*.json" -ErrorAction SilentlyContinue)
    $newClips = $afterClips | Where-Object { $beforeClips -notcontains $_.Name }

    foreach ($clipJson in $newClips) {
        Write-Host "`n>> New highlight captured: $($clipJson.Name)"
        
        # Step 1: AI Metadata & Curiosity Hook Generation (Gemini)
        Write-Host "Generating curiosity hooks and viral metadata with Gemini..."
        & powershell -ExecutionPolicy Bypass -File $runner enhance_metadata.py $clipJson.FullName --apply

        # Step 2: Auto-Publish with Anti-Spam Drip Queue (if -AutoPost is passed)
        if ($AutoPost) {
            $meta = Get-Content $clipJson.FullName -Raw | ConvertFrom-Json
            if ($meta.title -and -not $meta.zernio_post_id) {
                Write-Host "Evaluating clip against Drip Schedule (anti-spam pacing)..."
                & powershell -ExecutionPolicy Bypass -File $runner drip_scheduler.py $clipJson.FullName --publish
            }
        }
    }

    Write-Host "Sleeping 10s before next live check..."
    Start-Sleep -Seconds 10
}
