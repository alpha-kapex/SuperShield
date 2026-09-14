[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RuntimeRoleArn,
    [Parameter(Mandatory = $true)][string]$EntryPoint,
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
if ((Split-Path -Leaf $repoRoot) -ne "SuperShield") { throw "Refusing to deploy outside the SuperShield repository." }
$resolvedEntry = (Resolve-Path -LiteralPath (Join-Path $repoRoot $EntryPoint)).Path
if (-not $resolvedEntry.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) { throw "Entrypoint must be inside SuperShield." }

Push-Location $repoRoot
try {
  agentcore configure `
    --name supershield `
    --entrypoint $EntryPoint `
    --execution-role $RuntimeRoleArn `
    --region $Region
  Write-Host "Review generated .bedrock_agentcore.yaml, especially resource ARNs and network mode."
  agentcore launch
  agentcore status
}
finally {
  Pop-Location
}
