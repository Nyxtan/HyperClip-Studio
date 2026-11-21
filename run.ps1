param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Script,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ScriptArgs
)

$ErrorActionPreference = 'Stop'

# Resolve python in virtualenv or PATH
$python = 'python'
$venvPy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPy) {
    $python = $venvPy
}

# Avoid writing bytecode in the repo.
$env:PYTHONDONTWRITEBYTECODE = '1'

$target = Join-Path $PSScriptRoot $Script
if (-not (Test-Path -LiteralPath $target)) {
    throw "Script not found: $target"
}

& $python $target @ScriptArgs
exit $LASTEXITCODE
