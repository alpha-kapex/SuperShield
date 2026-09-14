# Standalone EC2 + Ollama live demo

This is the Bedrock-free deployment path for the public SuperShield demo. It runs the real Strands supervisor against Ollama on one ARM instance and serves the React application and FastAPI API from the same direct HTTP origin.

> Status: deployment artifacts only. Nothing in this guide has been deployed. Before running the script, independently confirm that the target account and principal are personal and are not associated with Kariant Development.

## Fixed deployment profile

| Item | Value | Reason |
|---|---|---|
| Region | `us-east-1` | The cost check in the script is deliberately scoped to one known price model. |
| Compute | `t4g.large`, 2 vCPU, 8 GiB, standard credits | Graviton is substantially cheaper than an M7i while remaining practical for a low-concurrency 8B quantized demo. Standard credits cannot create unlimited-mode CPU-credit charges; sustained traffic may throttle. |
| Model | `qwen3:8b-q4_K_M` | Stronger than the tiny local smoke-test model. Its registry layers were verified at about 4.87 GiB, fitting the 8 GiB host with a 4 GiB swap safety net and one-model/one-request limits. |
| Disk | 40 GiB encrypted gp3, 3,000 IOPS, 125 MiB/s | Holds the OS, build layers, model, logs, and swap. It is deleted with the instance. |
| State | One instance, in-memory store | Avoids DynamoDB/S3 and cross-instance consistency problems. Restarting the app clears cases and approvals. |
| Public URL | EC2 public DNS over HTTP | Avoids the account-blocked CloudFront dependency. The rate-limited gateway is the only public application port; do not submit sensitive or real customer data. |
| Admin | AWS Systems Manager Session Manager | There is no key pair, SSH listener, port 22 rule, NAT gateway, load balancer, or Elastic IP. |
| Cutoff | **2026-10-16 06:00 UTC** | This is 11:30 IST on Oct 16 and 23:00 PDT on Oct 15, leaving a buffer after the Oct 14 results date. |

At the cutoff, EventBridge invokes a narrowly scoped Lambda that terminates the EC2 instance (deleting its root EBS volume and releasing its public IPv4 address). The VPC, IAM roles, event rule, Lambda, and short-retention log group remain until the teardown script removes the stack, but they have no expected fixed hourly compute cost.

## Cost envelope

The deploy script refuses to run if its conservative plan exceeds $75. Its planning assumptions for `us-east-1` are:

- t4g.large on demand: $0.0672/hour;
- public IPv4: $0.005/hour;
- 40 GiB gp3: $0.08/GiB-month, prorated;
- $5 buffer for data transfer, Lambda, logs, and rounding.

A deployment around September 14 through the fixed cutoff is approximately **$64–65** under those assumptions. This is not an AWS quote, taxes and unusual data transfer are not included, and promotional credits may have service-specific eligibility. The nginx gateway limits model-start requests to reduce abuse. Delete early after judging whenever possible.

## Security boundary

- `SUPERSHIELD_PUBLIC_DEMO=true` and `SUPERSHIELD_ALLOW_INLINE_DOCUMENTS=false` restrict the API to repository fixtures.
- The app uses the memory store and exactly one instance.
- Ollama is reachable only on the private Docker network; the FastAPI container has no host port.
- The only host ingress is public TCP 80 to the rate-limited nginx gateway.
- The temporary URL is HTTP because this AWS account is not verified to create CloudFront distributions. Use only the included synthetic fixtures; arbitrary uploads are disabled.
- IMDSv2 is required with a hop limit of one, keeping instance credentials away from bridged containers.
- Containers drop Linux capabilities, use bounded memory/CPU, rotate local logs, and use read-only filesystems where practical.
- Session Manager is the only administrative route and is controlled by AWS IAM. Do not add an SSH rule.
- No Bedrock, AgentCore, DynamoDB, S3 application storage, NAT gateway, ALB, or EIP is used.

## Prerequisites

1. Independently verify that the AWS account is yours and is not Kariant-linked. Record the exact 12-digit account ID and the exact caller ARN from `aws sts get-caller-identity`.
2. Use a principal permitted to manage the narrowly named CloudFormation stack and its EC2/VPC, IAM instance/Lambda roles, Lambda, EventBridge, CloudWatch Logs, and SSM public AMI parameter resources. It also needs `iam:PassRole` for the two generated service roles.
3. Install AWS CLI v2 and Git. The script uses the current committed Git SHA; commit and push the deployment assets before running it.
4. Review current AWS prices and confirm that the remaining-hours estimate still fits the credits.

The current restricted `krishna` principal could not even validate CloudFormation or describe the project ECR repository, and account alias/organization ownership could not be checked. Do not run the deployment with that identity unless the account is independently confirmed and appropriate permissions are intentionally granted.

## Deploy

From the repository root in PowerShell:

```powershell
./infra/deploy-ec2-ollama.ps1 `
  -ExpectedAccountId '123456789012' `
  -ExpectedPrincipalArn 'arn:aws:iam::123456789012:user/your-personal-user' `
  -Stage 'devpost-2026' `
  -AcknowledgeEstimatedCost
```

For an assumed role, pass its exact STS caller ARN. The script:

1. refuses to run at or after the cutoff;
2. prints and enforces a conservative sub-$75 cost plan;
3. verifies both account ID and principal ARN;
4. refuses to update an existing stack, so an update cannot silently reset expectations;
5. deploys only the new, tagged networking and compute resources;
6. deploys the current immutable Git commit; and
7. waits up to 30 minutes for `/health` while the instance builds the app and downloads/warm-loads Qwen.

EC2 creation and the first model pull are slow. The URL may return a transient 502 until bootstrap completes. A `t4g.large` is deliberately economical, so sustained inference will be slower after standard CPU credits are consumed.

## Verify

```powershell
./infra/verify-deployment.ps1 -BaseUrl 'http://YOUR_EC2_PUBLIC_DNS'
python evals/run_benchmark.py --adapter http `
  --base-url 'http://YOUR_EC2_PUBLIC_DNS' `
  --output evals/results/ec2-ollama-20260914.json
```

Confirm `/health` reports `mode: strands`, `storage: memory`, and Ollama selected. Run at least the Priya flagship case and one prompt-injection case before adding the URL to Devpost.

If bootstrap fails, use Session Manager—never SSH:

```powershell
aws ssm start-session --region us-east-1 --target i-INSTANCEID
```

On the instance, inspect only SuperShield resources:

```bash
sudo tail -n 300 /var/log/supershield-bootstrap.log
sudo docker ps -a
sudo docker logs --tail 200 ollama
sudo docker logs --tail 200 supershield
sudo docker logs --tail 200 supershield-gateway
```

## Teardown

Delete early when judging is complete:

```powershell
./infra/teardown-ec2-ollama.ps1 `
  -ExpectedAccountId '123456789012' `
  -ExpectedPrincipalArn 'arn:aws:iam::123456789012:user/your-personal-user'
```

PowerShell asks for confirmation because this destroys the exact tagged stack. For a non-interactive, already-reviewed run, add `-Confirm:$false`.

If the automatic cutoff has already fired, the instance and root volume are gone; run the same teardown command to remove the remaining no-idle-cost resources.

## Operational limitations

- The state store is intentionally ephemeral. A process or instance restart clears sessions and cases.
- The first run loads the model and is slower. The boot process performs a warm-up before opening the gateway.
- SuperShield limits Ollama to one parallel request and nginx rate-limits run creation, but an overloaded or CPU-throttled instance can still time out.
- This is a short-lived hackathon demo, not a production architecture. Production would use durable state, multiple instances, asynchronous jobs, managed secrets, WAF controls, and a custom domain with end-to-end TLS.