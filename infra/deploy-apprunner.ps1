[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ImageIdentifier,
    [Parameter(Mandatory = $true)][string]$AgentCoreRuntimeArn,
    [Parameter(Mandatory = $true)][string]$AllowedOrigins,
    [string]$Region = "us-east-1",
    [string]$Stage = "demo"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
if ((Split-Path -Leaf $repoRoot) -ne "SuperShield") { throw "Refusing to deploy outside the SuperShield repository." }

function StackOutput([string]$name) {
  aws cloudformation describe-stacks --region $Region --stack-name "supershield-$Stage-core" `
    --query "Stacks[0].Outputs[?OutputKey=='$name'].OutputValue | [0]" --output text
}

$parameters = @(
  "Stage=$Stage",
  "ImageIdentifier=$ImageIdentifier",
  "AgentCoreRuntimeArn=$AgentCoreRuntimeArn",
  "AllowedOrigins=$AllowedOrigins",
  "InstanceRoleArn=$(StackOutput 'AppRunnerInstanceRoleArn')",
  "InstanceRoleName=$(StackOutput 'AppRunnerInstanceRoleName')",
  "EcrAccessRoleArn=$(StackOutput 'AppRunnerEcrAccessRoleArn')",
  "SessionSecretArn=$(StackOutput 'SessionSecretArn')",
  "CasesTableName=$(StackOutput 'CasesTableName')",
  "EvidenceBucketName=$(StackOutput 'EvidenceBucketName')",
  "DataKeyArn=$(StackOutput 'DataKeyArn')"
)

aws cloudformation deploy `
  --region $Region `
  --stack-name "supershield-$Stage-api" `
  --template-file (Join-Path $PSScriptRoot "cloudformation/apprunner.yaml") `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides $parameters

aws cloudformation describe-stacks --region $Region --stack-name "supershield-$Stage-api" `
  --query "Stacks[0].Outputs[].{Name:OutputKey,Value:OutputValue}" --output table
