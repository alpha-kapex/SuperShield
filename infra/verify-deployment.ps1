[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$BaseUrl)

$ErrorActionPreference = "Stop"
$base = $BaseUrl.TrimEnd('/')
$health = Invoke-RestMethod -Method Get -Uri "$base/health"
if ($health.status -notin @("ok", "healthy")) { throw "Unexpected health response: $($health | ConvertTo-Json -Compress)" }

$cases = Invoke-RestMethod -Method Get -Uri "$base/demo-cases"
if (@($cases).Count -lt 12 -and @($cases.cases).Count -lt 12) { throw "Expected all 12 curated demo cases." }

$created = Invoke-RestMethod -Method Post -Uri "$base/cases" -ContentType "application/json" `
  -Body (@{demo_case_id = "priya-saffron-route"} | ConvertTo-Json)
$caseId = if ($created.case_id) { $created.case_id } elseif ($created.caseId) { $created.caseId } else { $created.id }
if (-not $caseId) { throw "Case creation returned no id." }

$sessionId = "verify-$([guid]::NewGuid())"
$run = Invoke-RestMethod -Method Post -Uri "$base/cases/$caseId/runs" -ContentType "application/json" -Body (@{sessionId = $sessionId} | ConvertTo-Json)
$runId = if ($run.runId) { $run.runId } elseif ($run.run_id) { $run.run_id } else { $run.id }
if (-not $runId) { throw "Run creation returned no id." }
if ($run.status -notin @("COMPLETED", "WAITING_FOR_EVIDENCE")) {
  throw "Priya run did not reach a safe terminal state: $($run.status)"
}
if ($run.mode -ne "strands" -or $run.error -or $null -eq $run.packet) {
  throw "Priya run did not complete through Strands with a decision packet."
}

$packet = Invoke-RestMethod -Method Get -Uri "$base/cases/$caseId/decision-packet"
if ($packet.caseId -ne $caseId -or $null -eq $packet.validation) {
  throw "Decision packet verification failed for case $caseId."
}
$postRunHealth = Invoke-RestMethod -Method Get -Uri "$base/health"
$ollamaStatus = [string]$postRunHealth.optionalIntegrations.ollama
if ($postRunHealth.status -notin @("ok", "healthy") -or $ollamaStatus -notmatch "succeeded") {
  throw "The live Ollama/Strands invocation did not complete cleanly: $ollamaStatus"
}

Write-Host "Completed Priya smoke test for case $caseId (run $runId) via $ollamaStatus."
Write-Host "Run the HTTP benchmark for complete evidence, policy, and arithmetic checks:"
Write-Host "python evals/run_benchmark.py --adapter http --base-url $base"
