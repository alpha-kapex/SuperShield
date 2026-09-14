[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d{12}$')]
    [string]$ExpectedAccountId,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^arn:aws[a-z-]*:(iam|sts)::\d{12}:(user|role|assumed-role)/.+$')]
    [string]$ExpectedPrincipalArn,

    [ValidateSet('us-east-1')]
    [string]$Region = 'us-east-1',

    [ValidatePattern('^[a-z0-9-]{1,20}$')]
    [string]$Stage = 'devpost-2026'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if ((Split-Path -Leaf $repoRoot) -ne 'SuperShield') {
    throw 'Refusing to tear down resources outside the SuperShield repository workflow.'
}

$identityRaw = & aws sts get-caller-identity --region $Region --output json
if ($LASTEXITCODE -ne 0) { throw 'Unable to verify the AWS caller identity.' }
$identity = $identityRaw | ConvertFrom-Json
if ($identity.Account -ne $ExpectedAccountId) {
    throw "AWS account mismatch: expected $ExpectedAccountId, received $($identity.Account)."
}
if ($identity.Arn -ne $ExpectedPrincipalArn) {
    throw "AWS principal mismatch: expected $ExpectedPrincipalArn, received $($identity.Arn)."
}

$stackName = "supershield-$Stage-ec2-ollama"
$stackRaw = & aws cloudformation describe-stacks --region $Region --stack-name $stackName --output json
if ($LASTEXITCODE -ne 0) { throw "Unable to resolve exact stack $stackName." }
$stack = $stackRaw | ConvertFrom-Json
$projectTag = $stack.Stacks[0].Tags | Where-Object { $_.Key -eq 'Project' }
if (-not $projectTag -or $projectTag.Value -ne 'SuperShield') {
    throw "Stack $stackName is not tagged Project=SuperShield; refusing deletion."
}

if ($PSCmdlet.ShouldProcess("AWS stack $stackName in account $ExpectedAccountId", 'Delete and wait for complete teardown')) {
    & aws cloudformation delete-stack --region $Region --stack-name $stackName
    if ($LASTEXITCODE -ne 0) { throw 'CloudFormation delete request failed.' }
    & aws cloudformation wait stack-delete-complete --region $Region --stack-name $stackName
    if ($LASTEXITCODE -ne 0) { throw 'CloudFormation stack deletion did not complete successfully.' }
    Write-Host "Deleted $stackName. The EC2 instance, root volume, network, and scoped IAM resources are removed."
}