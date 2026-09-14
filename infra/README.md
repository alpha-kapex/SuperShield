# AWS deployment

For the short-lived, Bedrock-free live demo, use the standalone [EC2 + Ollama deployment](EC2_OLLAMA_DEPLOYMENT.md). It runs `qwen3:8b-q4_K_M` on one ARM `t4g.large`, exposes HTTPS through CloudFront, and has a fixed post-results cost cutoff. The AgentCore/App Runner path below remains an optional future architecture.

This deployment keeps the public surface small: App Runner exposes the FastAPI BFF, the BFF invokes the SuperShield supervisor in Amazon Bedrock AgentCore Runtime, and ephemeral state is encrypted in DynamoDB and S3. CloudWatch receives structured events and traces. The public demo loads only repository fixtures; it does not accept arbitrary uploads or external email recipients.

## What is provisioned

| Template | Resources | Retention / boundary |
|---|---|---|
| `cloudformation/core.yaml` | KMS key, private S3 bucket, DynamoDB table, log groups, ECR repository, runtime and App Runner roles | S3 objects and versions expire after one day by default; DynamoDB uses the `ExpiresAt` TTL; logs retain 14 days. |
| `cloudformation/budget.yaml` | Monthly AWS Budget | Forecast at 80%, actual at 100%; email confirmation is required. |
| `cloudformation/apprunner.yaml` | App Runner service, autoscaling, X-Ray observability | One minimum and two maximum instances; curated public API only. |
| `agentcore/.bedrock_agentcore.template.yaml` | Reviewable AgentCore deployment contract | Generated identifiers and secrets stay uncommitted. |

The roles intentionally have no wildcard data resources. AgentCore can invoke only Nova Pro and Nova Lite, access only the case table and `cases/*` evidence prefix, use the project KMS key, and write to the project log group. App Runner receives only its session secret and project resources. SES is absent unless a team explicitly adds a verified, team-owned test identity.

## Prerequisites

1. Choose an AWS account dedicated to the demo and a region supporting Amazon Nova, Bedrock AgentCore, and App Runner (examples use `us-east-1`).
2. Enable model access for `amazon.nova-pro-v1:0` and `amazon.nova-lite-v1:0`.
3. Install AWS CLI v2, Docker, Python 3.12, and the current Bedrock AgentCore starter toolkit (`agentcore --version`). Authenticate with a short-lived role, not access keys in `.env`.
4. Confirm the operator may deploy CloudFormation, IAM roles with the included policies, KMS, S3, DynamoDB, ECR, App Runner, CloudWatch, Secrets Manager, and Budgets.
5. Copy `.env.example` to `.env` only for local use. Never commit `.env`.

## 1. Validate before spending

```powershell
aws cloudformation validate-template --region us-east-1 --template-body file://infra/cloudformation/core.yaml
aws cloudformation validate-template --region us-east-1 --template-body file://infra/cloudformation/apprunner.yaml
aws cloudformation validate-template --region us-east-1 --template-body file://infra/cloudformation/budget.yaml
python evals/run_benchmark.py --adapter oracle
```

The first deployment creates billable resources. Review AWS pricing in your selected region; prices change.

## 2. Create the data plane and budget

```powershell
./infra/deploy-core.ps1 -Region us-east-1 -Stage demo `
  -BudgetEmail owner@example.com -MonthlyBudgetUsd 25
```

Confirm the AWS Budgets subscription email. The script prints all stack outputs. Save the `RuntimeExecutionRoleArn`, table, bucket, log group, and repository URI for the next steps.

The application must write a Unix-epoch `ExpiresAt` value no more than 24 hours after case creation. DynamoDB TTL deletion is asynchronous; the API must enforce expiry at read time too. S3 lifecycle deletion is also asynchronous, so `DELETE /cases/{caseId}` should remove the case prefix immediately.

## 3. Deploy the Strands supervisor to AgentCore Runtime

First confirm the repository's AgentCore entrypoint. It must expose the supervisor and its bounded tools, not the App Runner BFF. Then run:

```powershell
$runtimeRole = aws cloudformation describe-stacks --region us-east-1 `
  --stack-name supershield-demo-core `
  --query "Stacks[0].Outputs[?OutputKey=='RuntimeExecutionRoleArn'].OutputValue | [0]" --output text

./infra/agentcore/deploy.ps1 -Region us-east-1 `
  -RuntimeRoleArn $runtimeRole `
  -EntryPoint src/supershield/integrations/agentcore.py
```

`agentcore configure` writes the real `.bedrock_agentcore.yaml`; compare it with the committed template, ensure observability is enabled, and keep generated account IDs out of Git. Record the runtime ARN returned by `agentcore status`. If the implementation uses a different filename, pass that repository-relative path explicitly.

After deployment, set the environment names in the generated configuration from the core stack outputs. Do not put credentials or the session-secret plaintext in that file. AgentCore obtains AWS credentials from `RuntimeExecutionRoleArn`.

## 4. Build and push the API image

Use an immutable tag such as the Git commit SHA:

```powershell
$tag = git rev-parse --short=12 HEAD
$image = ./infra/build-and-push.ps1 -Region us-east-1 -Stage demo -ImageTag $tag
```

ECR scans each push. Inspect the scan and stop if any critical finding is unreviewed:

```powershell
aws ecr describe-image-scan-findings --region us-east-1 `
  --repository-name supershield-demo --image-id imageTag=$tag
```

## 5. Deploy App Runner

```powershell
./infra/deploy-apprunner.ps1 `
  -Region us-east-1 -Stage demo `
  -ImageIdentifier $image `
  -AgentCoreRuntimeArn 'arn:aws:bedrock-agentcore:REGION:ACCOUNT:runtime/REPLACE' `
  -AllowedOrigins 'https://your-static-demo.example'
```

Auto-deployment is deliberately disabled: every release is an explicit immutable image. App Runner retrieves the session secret from Secrets Manager. The API must enforce origin, body-size, case-count, token, and rate limits even though the UI exposes only curated cases.

## 6. Verify and observe

```powershell
./infra/verify-deployment.ps1 -BaseUrl 'https://YOUR_SERVICE.awsapprunner.com'
python evals/run_benchmark.py --adapter http `
  --base-url 'https://YOUR_SERVICE.awsapprunner.com' `
  --output evals/results/agentcore-YYYYMMDD.json
```

Inspect AgentCore traces and `/aws/supershield/demo/agentcore`. Logs must contain run IDs, tool names, timings, decision-state transitions, and citation IDs—not document bodies, secrets, approval tokens, or private chain-of-thought. Test deletion and expiry before publishing the URL.

## Cost controls

- Default budget: **$25/month**, with forecast notification at 80% and actual notification at 100%.
- App Runner is capped at two instances; lower the service to zero/delete it outside judging windows if a continuously available demo is unnecessary.
- DynamoDB is on-demand, evidence expires after one day, logs after 14 days, and ECR retains ten images.
- The public demo caps runs per session and Bedrock output tokens. Nova Lite handles extraction; Nova Pro is reserved for synthesis.
- `estimated_cost_usd` in benchmark output must come from actual token counts and current regional prices. Do not copy the local oracle's `$0` into a submission claim.

## Teardown

Delete in this order: App Runner stack, AgentCore runtime, all case objects/versions, core stack, then budget stack. Export any benchmark evidence first. S3 refuses stack deletion while versions remain; prefer waiting for the one-day lifecycle or use a reviewed, bucket-specific version-deletion procedure. Never run a broad account-wide cleanup command.
