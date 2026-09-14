[CmdletBinding()]
param(
    [string]$Region = "us-east-1",
    [string]$Stage = "demo",
    [string]$ImageTag = "latest"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
if ((Split-Path -Leaf $repoRoot) -ne "SuperShield") { throw "Refusing to build outside the SuperShield repository." }

$repositoryUri = aws cloudformation describe-stacks `
  --region $Region `
  --stack-name "supershield-$Stage-core" `
  --query "Stacks[0].Outputs[?OutputKey=='ContainerRepositoryUri'].OutputValue | [0]" `
  --output text
if (-not $repositoryUri -or $repositoryUri -eq "None") { throw "ContainerRepositoryUri output not found." }
$registry = $repositoryUri.Split('/')[0]

aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $registry
docker build --pull --tag "supershield:$ImageTag" $repoRoot
docker tag "supershield:$ImageTag" "${repositoryUri}:$ImageTag"
docker push "${repositoryUri}:$ImageTag"
Write-Output "${repositoryUri}:$ImageTag"
