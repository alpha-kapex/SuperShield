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

$run = Invoke-RestMethod -Method Post -Uri "$base/cases/$caseId/runs" -ContentType "application/json" -Body "{}"
Write-Host "Started Priya smoke test for case $caseId (run $($run.id)$($run.run_id))."
Write-Host "Run the HTTP benchmark for complete evidence, policy, and arithmetic checks:"
Write-Host "python evals/run_benchmark.py --adapter http --base-url $base"
