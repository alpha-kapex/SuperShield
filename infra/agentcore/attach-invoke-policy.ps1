[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$AgentCoreRuntimeArn,
    [string]$Region = "us-east-1",
    [string]$Stage = "demo"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$roleArn = aws cloudformation describe-stacks --region $Region --stack-name "supershield-$Stage-core" `
  --query "Stacks[0].Outputs[?OutputKey=='AppRunnerInstanceRoleArn'].OutputValue | [0]" --output text
if (-not $roleArn -or $roleArn -eq "None") { throw "AppRunnerInstanceRoleArn output not found." }
$roleName = ($roleArn -split '/')[-1]

aws cloudformation deploy `
  --region $Region `
  --stack-name "supershield-$Stage-runtime-invoke" `
  --template-file (Join-Path $PSScriptRoot "..\cloudformation\runtime-invoke-policy.yaml") `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides "Stage=$Stage" "AppRunnerInstanceRoleName=$roleName" "AgentCoreRuntimeArn=$AgentCoreRuntimeArn"

Write-Host "Attached an exact-runtime invoke policy to $roleName."
