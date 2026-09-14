from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "infra" / "cloudformation" / "ec2-ollama.yaml").read_text(
    encoding="utf-8"
)
DEPLOY_SCRIPT = (ROOT / "infra" / "deploy-ec2-ollama.ps1").read_text(
    encoding="utf-8"
)
TEARDOWN_SCRIPT = (ROOT / "infra" / "teardown-ec2-ollama.ps1").read_text(
    encoding="utf-8"
)
OLLAMA_DOCKERFILE = (ROOT / "infra" / "ec2" / "Dockerfile").read_text(
    encoding="utf-8"
)


def test_ec2_demo_has_fixed_budget_profile() -> None:
    assert "Default: t4g.large" in TEMPLATE
    assert "CPUCredits: standard" in TEMPLATE
    assert "Default: 40" in TEMPLATE
    assert "MaxValue: 40" in TEMPLATE
    assert "Encrypted: true" in TEMPLATE
    assert "DeleteOnTermination: true" in TEMPLATE
    assert "al2023-ami-kernel-default-arm64" in TEMPLATE
    assert "qwen3:8b-q4_K_M" in TEMPLATE
    assert "OLLAMA_NUM_PARALLEL=1" in TEMPLATE
    assert "OLLAMA_CONTEXT_LENGTH=4096" in TEMPLATE


def test_ec2_demo_has_no_open_admin_path_or_costly_network_middlebox() -> None:
    assert "FromPort: 22" not in TEMPLATE
    assert "ToPort: 22" not in TEMPLATE
    assert "AWS::EC2::NatGateway" not in TEMPLATE
    assert "AWS::EC2::EIP" not in TEMPLATE
    assert "AWS::ElasticLoadBalancingV2" not in TEMPLATE
    assert "SourcePrefixListId: !Ref CloudFrontOriginPrefixListId" in TEMPLATE
    assert "HttpTokens: required" in TEMPLATE
    assert "HttpPutResponseHopLimit: 1" in TEMPLATE
    assert "AmazonSSMManagedInstanceCore" in TEMPLATE


def test_public_origin_is_https_only_and_curated() -> None:
    assert "ViewerProtocolPolicy: redirect-to-https" in TEMPLATE
    assert "CloudFrontDefaultCertificate: true" in TEMPLATE
    assert "X-SuperShield-Origin" in TEMPLATE
    assert "__ORIGIN_VERIFY_SECRET__" in TEMPLATE
    assert "SUPERSHIELD_STORAGE_BACKEND=memory" in TEMPLATE
    assert "SUPERSHIELD_PUBLIC_DEMO=true" in TEMPLATE
    assert "SUPERSHIELD_ALLOW_INLINE_DOCUMENTS=false" in TEMPLATE
    assert "--publish 8080:8080" in TEMPLATE
    assert "--publish 8000:8000" not in TEMPLATE


def test_results_cutoff_terminates_compute_and_disables_edge() -> None:
    assert "cron(0 6 16 10 ? 2026)" in TEMPLATE
    assert "2026-10-16T06:00:00Z" in TEMPLATE
    assert "ec2:TerminateInstances" in TEMPLATE
    assert "cloudfront:UpdateDistribution" in TEMPLATE
    assert 'config["Enabled"] = False' in TEMPLATE
    assert "rate(5 days)" not in TEMPLATE


def test_ec2_path_has_no_bedrock_or_agentcore_dependency() -> None:
    assert "bedrock" not in TEMPLATE.lower()
    assert "agentcore" not in TEMPLATE.lower()
    assert '".[ollama]"' in OLLAMA_DOCKERFILE
    assert '".[aws]"' not in OLLAMA_DOCKERFILE


def test_scripts_require_identity_and_cost_acknowledgement() -> None:
    assert "ExpectedAccountId" in DEPLOY_SCRIPT
    assert "ExpectedPrincipalArn" in DEPLOY_SCRIPT
    assert "AcknowledgeEstimatedCost" in DEPLOY_SCRIPT
    assert "estimatedUpperPlan -gt 75" in DEPLOY_SCRIPT
    assert "Refusing an update" in DEPLOY_SCRIPT
    assert "ExpectedAccountId" in TEARDOWN_SCRIPT
    assert "ExpectedPrincipalArn" in TEARDOWN_SCRIPT
    assert "Project=SuperShield" in TEARDOWN_SCRIPT