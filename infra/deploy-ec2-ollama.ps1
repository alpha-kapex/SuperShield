[CmdletBinding()]
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
    [string]$Stage = 'devpost-2026',

    [ValidatePattern('^[A-Fa-f0-9]{40}$')]
    [string]$GitRef,

    [switch]$AcknowledgeEstimatedCost
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if ((Split-Path -Leaf $repoRoot) -ne 'SuperShield') {
    throw 'Refusing to deploy outside the SuperShield repository.'
}
if (-not $AcknowledgeEstimatedCost) {
    throw 'Re-run with -AcknowledgeEstimatedCost after reviewing infra/EC2_OLLAMA_DEPLOYMENT.md.'
}

$cutoff = [DateTimeOffset]::Parse('2026-10-16T06:00:00Z')
$now = [DateTimeOffset]::UtcNow
if ($now -ge $cutoff) {
    throw "The automatic cost-teardown cutoff ($($cutoff.ToString('u'))) has passed. Update and review the template before deploying."
}

# Conservative us-east-1 planning values, not a quote: t4g.large $0.0672/hour,
# public IPv4 $0.005/hour, gp3 $0.08/GB-month, plus a $5 usage buffer.
$remainingHours = [Math]::Ceiling(($cutoff - $now).TotalHours)
$estimatedCompute = $remainingHours * 0.0672
$estimatedIpv4 = $remainingHours * 0.005
$estimatedStorage = 40 * 0.08 * ($remainingHours / 720)
$estimatedUpperPlan = $estimatedCompute + $estimatedIpv4 + $estimatedStorage + 5
if ($estimatedUpperPlan -gt 75) {
    throw ('Planned cost through the cutoff is ${0:N2}, above the $75 limit. Do not deploy.' -f $estimatedUpperPlan)
}
Write-Host ('Conservative planned cost through {0:u}: ${1:N2} (before taxes or unusual data transfer).' -f $cutoff, $estimatedUpperPlan)

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
$existing = & aws cloudformation describe-stacks --region $Region --stack-name $stackName --output json 2>&1
if ($LASTEXITCODE -eq 0) {
    throw "Stack $stackName already exists. Refusing an update that could extend the fixed cost window; tear it down explicitly first."
}
if (($existing -join "`n") -notmatch 'does not exist') {
    throw "Could not prove that stack $stackName is absent: $($existing -join ' ')"
}

if (-not $GitRef) {
    $GitRef = (& git -C $repoRoot rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $GitRef -notmatch '^[A-Fa-f0-9]{40}$') {
        throw 'Could not resolve an immutable Git commit SHA.'
    }
}

$prefixListId = (& aws ec2 describe-managed-prefix-lists `
    --region $Region `
    --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing `
    --query 'PrefixLists[0].PrefixListId' `
    --output text).Trim()
if ($LASTEXITCODE -ne 0 -or $prefixListId -notmatch '^pl-[a-f0-9]+$') {
    throw 'Could not resolve the CloudFront origin-facing managed prefix list.'
}

$secretBytes = [byte[]]::new(48)
[Security.Cryptography.RandomNumberGenerator]::Fill($secretBytes)
$originSecret = [Convert]::ToBase64String($secretBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
$template = Join-Path $PSScriptRoot 'cloudformation/ec2-ollama.yaml'

& aws cloudformation validate-template --region $Region --template-body "file://$template" | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'CloudFormation template validation failed.' }

$parameters = @(
    "Stage=$Stage",
    'InstanceType=t4g.large',
    'RootVolumeGiB=40',
    "GitRef=$GitRef",
    'OllamaModel=qwen3:8b-q4_K_M',
    "CloudFrontOriginPrefixListId=$prefixListId",
    "OriginVerifySecret=$originSecret"
)
& aws cloudformation deploy `
    --region $Region `
    --stack-name $stackName `
    --template-file $template `
    --capabilities CAPABILITY_IAM `
    --parameter-overrides $parameters `
    --tags Project=SuperShield Purpose=public-curated-demo AutoTeardownUtc=2026-10-16T06-00-00Z
if ($LASTEXITCODE -ne 0) { throw 'CloudFormation deployment failed.' }

$url = (& aws cloudformation describe-stacks `
    --region $Region `
    --stack-name $stackName `
    --query "Stacks[0].Outputs[?OutputKey=='PublicUrl'].OutputValue | [0]" `
    --output text).Trim()
if ($LASTEXITCODE -ne 0 -or $url -notmatch '^https://') {
    throw 'Deployment completed but no HTTPS output URL was returned.'
}

Write-Host "CloudFormation is ready; the ARM instance is still building the app and pulling Qwen."
Write-Host "Public URL: $url"
$healthy = $false
for ($attempt = 1; $attempt -le 120; $attempt++) {
    try {
        $health = Invoke-RestMethod -Method Get -Uri "$url/health" -TimeoutSec 10
        if ($health.status -in @('ok', 'healthy')) {
            $healthy = $true
            Write-Host ($health | ConvertTo-Json -Depth 8)
            break
        }
    } catch {
        if ($attempt % 6 -eq 0) {
            Write-Host "Waiting for model bootstrap ($($attempt * 15) seconds elapsed)..."
        }
    }
    Start-Sleep -Seconds 15
}
if (-not $healthy) {
    Write-Warning "The stack exists but did not become healthy within 30 minutes. Use Session Manager and inspect /var/log/supershield-bootstrap.log."
    exit 2
}

Write-Host "SuperShield is live at $url"
Write-Host "Automatic cost teardown: 2026-10-16 06:00 UTC (EC2/root EBS terminated; CloudFront disabled)."