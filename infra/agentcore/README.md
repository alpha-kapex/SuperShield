# AgentCore runtime handoff

The backend entrypoint is `src/supershield/integrations/agentcore.py`, exposing `supershield.integrations.agentcore:invoke`. Deploy the file with the current Bedrock AgentCore starter toolkit; CLI-generated identifiers remain uncommitted.

```powershell
$runtimeRole = aws cloudformation describe-stacks --region us-east-1 `
  --stack-name supershield-demo-core `
  --query "Stacks[0].Outputs[?OutputKey=='RuntimeExecutionRoleArn'].OutputValue | [0]" --output text

./infra/agentcore/deploy.ps1 -Region us-east-1 `
  -RuntimeRoleArn $runtimeRole `
  -EntryPoint src/supershield/integrations/agentcore.py
```

Review the generated `.bedrock_agentcore.yaml` against `.bedrock_agentcore.template.yaml`, inject the core stack's table/bucket/log names as runtime environment variables, launch, and obtain the exact runtime ARN with `agentcore status`.

Then attach the BFF's one-runtime permission:

```powershell
./infra/agentcore/attach-invoke-policy.ps1 -Region us-east-1 -Stage demo `
  -AgentCoreRuntimeArn 'arn:aws:bedrock-agentcore:REGION:ACCOUNT:runtime/REPLACE'
```

This separate stack avoids a wildcard runtime ARN and resolves the deployment-order dependency: core resources → AgentCore runtime → exact invoke policy → App Runner.
