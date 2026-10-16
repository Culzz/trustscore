# Smoke test for a running TrustScore API.
#   powershell -ExecutionPolicy Bypass -File scripts/smoke.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/smoke.ps1 -BaseUrl https://your-app.vercel.app/api
param(
    [string]$BaseUrl = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"
$applicant = @{
    person_age                  = 31
    person_income               = 42000
    person_home_ownership       = "RENT"
    person_emp_length           = 4
    loan_intent                 = "MEDICAL"
    loan_grade                  = "E"
    loan_amnt                   = 10000
    loan_int_rate               = 15.5
    cb_person_default_on_file   = "N"
    cb_person_cred_hist_length  = 6
}
$json = $applicant | ConvertTo-Json

function Show($name, $value) {
    Write-Host ("{0,-16} {1}" -f $name, $value)
}

Write-Host "TrustScore smoke test -> $BaseUrl" -ForegroundColor Cyan
Write-Host ("-" * 56)

$health = Invoke-RestMethod "$BaseUrl/health"
Show "GET /health" "status=$($health.status) model=$($health.model_loaded) v=$($health.model_version)"

$model = Invoke-RestMethod "$BaseUrl/model"
Show "GET /model" "v=$($model.version) auc=$($model.metrics.calibrated.roc_auc)"

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$predict = Invoke-RestMethod "$BaseUrl/predict" -Method Post -ContentType "application/json" -Body $json
$sw.Stop()
Show "POST /predict" ("pd={0:N4} band={1} in {2} ms" -f $predict.probability_of_default, $predict.band, $sw.ElapsedMilliseconds)

$explain = Invoke-RestMethod "$BaseUrl/explain" -Method Post -ContentType "application/json" -Body $json
Show "POST /explain" "$($explain.reasons.Count) reasons e.g. '$($explain.reasons[0].text)'"

$decision = Invoke-RestMethod "$BaseUrl/decision" -Method Post -ContentType "application/json" -Body "{`"applicant`":$json}"
Show "POST /decision" "decision=$($decision.decision) simulated=$($decision.simulated) cost=$([math]::Round($decision.expected_cost,2))"

$cf = Invoke-RestMethod "$BaseUrl/counterfactual" -Method Post -ContentType "application/json" -Body $json
Show "POST /cf" "band=$($cf.current_band) scenarios=$($cf.scenarios.Count)"

$stats = Invoke-RestMethod "$BaseUrl/stats"
Show "GET /stats" "enabled=$($stats.enabled) total=$($stats.total_predictions)"

Write-Host ("-" * 56)
Write-Host "OK" -ForegroundColor Green
