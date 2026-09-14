[CmdletBinding()]
param(
    [string]$Region = "us-east-1",
    [string]$Stage = "demo",
    [Parameter(Mandatory = $true)][string]$BudgetEmail,
    [decimal]$MonthlyBudgetUsd = 25
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
if ((Split-Path -Leaf $repoRoot) -ne "SuperShield") { throw "Refusing to deploy outside the SuperShield repository." }

aws sts get-caller-identity --region $Region | Out-Null
aws cloudformation deploy `
  --region $Region `
  --stack-name "supershield-$Stage-core" `
  --template-file (Join-Path $PSScriptRoot "cloudformation/core.yaml") `
  --capabilities CAPABILITY_NAMED_IAM `
  --parameter-overrides "Stage=$Stage"

aws cloudformation deploy `
  --region $Region `
  --stack-name "supershield-$Stage-budget" `
  --template-file (Join-Path $PSScriptRoot "cloudformation/budget.yaml") `
  --parameter-overrides "NotificationEmail=$BudgetEmail" "MonthlyBudgetUsd=$MonthlyBudgetUsd"

aws cloudformation describe-stacks `
  --region $Region `
  --stack-name "supershield-$Stage-core" `
  --query "Stacks[0].Outputs[].{Name:OutputKey,Value:OutputValue}" `
  --output table

Write-Host "Confirm the AWS Budgets email subscription before continuing."
