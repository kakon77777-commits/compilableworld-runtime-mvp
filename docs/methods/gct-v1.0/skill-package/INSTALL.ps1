param(
    [string]$ClaudeHome = "$env:USERPROFILE\.claude"
)

$ErrorActionPreference = "Stop"

$Source = Join-Path $PSScriptRoot "global-first-completion\SKILL.md"
$DestinationDir = Join-Path $ClaudeHome "skills\global-first-completion"
$Destination = Join-Path $DestinationDir "SKILL.md"

if (-not (Test-Path $Source)) {
    throw "SKILL.md not found: $Source"
}

New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
Copy-Item -Force $Source $Destination

Write-Host "Installed global-first-completion skill:"
Write-Host "  $Destination"
Write-Host ""
Write-Host "Restart Claude Code if the skill is not immediately detected."
