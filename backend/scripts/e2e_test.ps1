# scripts/e2e_test.ps1
# Full end-to-end test: Ingestion -> Query -> Rate Limiting
# Run from: D:\RAG_Ops\backend
# Prerequisites: docker-compose up -d (all containers healthy)

$BASE = "http://localhost:8000"
$HEADERS = @{ "Content-Type" = "application/json" }

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "  RAG_Ops End-to-End Test Suite" -ForegroundColor Cyan
Write-Host "==========================================`n" -ForegroundColor Cyan

# -----------------------------------------------------------------------------
# STEP 1 - Register a test user
# -----------------------------------------------------------------------------
Write-Host "[ STEP 1 ] Registering test user..." -ForegroundColor Yellow

$registerBody = @{
    email    = "test_e2e@ragops.dev"
    password = "TestPass123!"
    name     = "E2E Tester"
} | ConvertTo-Json

try {
    $registerResp = Invoke-RestMethod `
        -Uri "$BASE/auth/register" `
        -Method POST `
        -Body $registerBody `
        -ContentType "application/json" `
        -ErrorAction Stop
    Write-Host "  [OK] Registered: $($registerResp.email)" -ForegroundColor Green
} catch {
    Write-Host "  [INFO] User may already exist - continuing to login" -ForegroundColor Gray
}

# -----------------------------------------------------------------------------
# STEP 2 - Login and get JWT token
# -----------------------------------------------------------------------------
Write-Host "`n[ STEP 2 ] Logging in..." -ForegroundColor Yellow

$loginBody = "username=test_e2e@ragops.dev&password=TestPass123!"

$loginResp = Invoke-RestMethod `
    -Uri "$BASE/auth/token" `
    -Method POST `
    -Body $loginBody `
    -ContentType "application/x-www-form-urlencoded"

$TOKEN = $loginResp.access_token
$AUTH  = @{ "Authorization" = "Bearer $TOKEN" }
Write-Host "  [OK] Token obtained (${TOKEN.Substring(0,20)}...)" -ForegroundColor Green

# -----------------------------------------------------------------------------
# STEP 3 - Get workspace_id from profile
# -----------------------------------------------------------------------------
Write-Host "`n[ STEP 3 ] Fetching workspace ID..." -ForegroundColor Yellow

$profile = Invoke-RestMethod `
    -Uri "$BASE/auth/me" `
    -Method GET `
    -Headers $AUTH

# PS 5.1 safe null-coalescing
$WORKSPACE_ID = $null
if ($profile.workspace_id) { $WORKSPACE_ID = $profile.workspace_id }
elseif ($profile.workspaces -and $profile.workspaces.Count -gt 0) { $WORKSPACE_ID = $profile.workspaces[0].id }
elseif ($profile.workspace.id) { $WORKSPACE_ID = $profile.workspace.id }

Write-Host "  [OK] Workspace ID: $WORKSPACE_ID" -ForegroundColor Green

# -----------------------------------------------------------------------------
# PHASE A - INGESTION PIPELINE TEST
# -----------------------------------------------------------------------------

Write-Host "`n==========================================" -ForegroundColor Magenta
Write-Host "  PHASE A: Ingestion Pipeline" -ForegroundColor Magenta
Write-Host "==========================================" -ForegroundColor Magenta

# -----------------------------------------------------------------------------
# STEP 4 - Upload a sample document
# -----------------------------------------------------------------------------
Write-Host "`n[ STEP 4 ] Uploading sample_docs/rag_overview.txt..." -ForegroundColor Yellow

$filePath = ".\sample_docs\rag_overview.txt"
$fileName = "rag_overview.txt"
$fileBytes = [System.IO.File]::ReadAllBytes((Resolve-Path $filePath))
$boundary  = [System.Guid]::NewGuid().ToString()

$bodyLines = @(
    "--$boundary",
    "Content-Disposition: form-data; name=`"file`"; filename=`"$fileName`"",
    "Content-Type: text/plain",
    "",
    [System.Text.Encoding]::UTF8.GetString($fileBytes),
    "--$boundary--"
)
$multipartBody = $bodyLines -join "`r`n"

$uploadResp = Invoke-RestMethod `
    -Uri "$BASE/documents/upload" `
    -Method POST `
    -Headers $AUTH `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($multipartBody)) `
    -ContentType "multipart/form-data; boundary=$boundary"

$DOC_ID = $uploadResp.document_id
Write-Host "  [OK] Uploaded - document_id: $DOC_ID" -ForegroundColor Green
Write-Host "  [INFO] Status: $($uploadResp.status)" -ForegroundColor Gray

# -----------------------------------------------------------------------------
# STEP 5 - Poll document status until ready (max 60s)
# -----------------------------------------------------------------------------
Write-Host "`n[ STEP 5 ] Polling document status (Celery worker processing)..." -ForegroundColor Yellow

$maxWait  = 60
$interval = 3
$elapsed  = 0
$status   = "pending"

while ($status -notin @("ready", "failed") -and $elapsed -lt $maxWait) {
    Start-Sleep -Seconds $interval
    $elapsed += $interval

    $statusResp = Invoke-RestMethod `
        -Uri "$BASE/documents/$DOC_ID/status" `
        -Method GET `
        -Headers $AUTH

    $status = $statusResp.status
    $chunks = if ($null -ne $statusResp.chunks_created) { $statusResp.chunks_created } else { '?' }
    Write-Host "  [WAIT] [$elapsed`s] Status: $status - chunks: $chunks" -ForegroundColor Gray
}

if ($status -eq "ready") {
    Write-Host "  [OK] Document READY - chunks created: $($statusResp.chunks_created)" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Document status: $status after ${elapsed}s - check celery_worker logs" -ForegroundColor Red
    Write-Host "     Run: docker-compose logs celery_worker" -ForegroundColor Red
    exit 1
}

# -----------------------------------------------------------------------------
# STEP 6 - Verify eval_results rows were created
# -----------------------------------------------------------------------------
Write-Host "`n[ STEP 6 ] Verifying eval_results in database..." -ForegroundColor Yellow

$evalCheck = docker exec ragops_postgres psql -U postgres -d ragops -t -c `
    "SELECT COUNT(*) FROM eval_results WHERE document_id = '$DOC_ID';"

$evalCount = $evalCheck.Trim()
if ([int]$evalCount -gt 0) {
    Write-Host "  [OK] eval_results rows: $evalCount (RAGAS evaluation ran)" -ForegroundColor Green
} else {
    Write-Host "  [WARN] eval_results rows: 0 - RAGAS may be disabled or LLM failed" -ForegroundColor DarkYellow
    Write-Host "     Check: RAGAS_ENABLED in .env and celery_worker logs" -ForegroundColor Gray
}

# -----------------------------------------------------------------------------
# PHASE B - QUERY PIPELINE TEST
# -----------------------------------------------------------------------------

Write-Host "`n==========================================" -ForegroundColor Magenta
Write-Host "  PHASE B: Query Pipeline (SSE Stream)" -ForegroundColor Magenta
Write-Host "==========================================" -ForegroundColor Magenta

# -----------------------------------------------------------------------------
# STEP 7 - Send a query and verify SSE events
# -----------------------------------------------------------------------------
Write-Host "`n[ STEP 7 ] Sending query - checking SSE event sequence..." -ForegroundColor Yellow

$queryBody = @{
    query        = "What is retrieval augmented generation and how does it work?"
    workspace_id = $WORKSPACE_ID
    top_k        = 5
} | ConvertTo-Json

$request = [System.Net.HttpWebRequest]::Create("$BASE/query")
$request.Method  = "POST"
$request.Headers.Add("Authorization", "Bearer $TOKEN")
$request.ContentType = "application/json"

$bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($queryBody)
$request.ContentLength = $bodyBytes.Length
$stream = $request.GetRequestStream()
$stream.Write($bodyBytes, 0, $bodyBytes.Length)
$stream.Close()

$response = $request.GetResponse()
$reader   = New-Object System.IO.StreamReader($response.GetResponseStream())

$events       = @()
$tokenCount   = 0
$hasCitations = $false
$hasDone      = $false

Write-Host "  Receiving SSE stream..." -ForegroundColor Gray

while (-not $reader.EndOfStream) {
    $line = $reader.ReadLine()
    if ($line -match "^data: (.+)$") {
        $raw = $Matches[1]
        try {
            $parsed = $raw | ConvertFrom-Json
            $eventType = if ($parsed.event) { $parsed.event } else { "token" }
            $events += $eventType

            switch ($eventType) {
                "token"     { $tokenCount++; Write-Host "." -NoNewline -ForegroundColor Cyan }
                "citations" { $hasCitations = $true; Write-Host "`n  [ATTACH] Citations received: $($parsed.data.Count)" -ForegroundColor Green }
                "critic"    { Write-Host "  [CRITIC] Critic received" -ForegroundColor Green }
                "done"      { $hasDone = $true; Write-Host "  [DONE] Done event received" -ForegroundColor Green }
                "error"     { Write-Host "`n  [FAIL] Error event: $($parsed.data)" -ForegroundColor Red }
            }
        } catch {
            $tokenCount++
            Write-Host "." -NoNewline -ForegroundColor Cyan
        }
    }
}
$reader.Close()

Write-Host ""
if ($tokenCount -gt 0 -and $hasCitations -and $hasDone) {
    Write-Host "  [OK] Query pipeline PASSED" -ForegroundColor Green
    Write-Host "     Tokens received : $tokenCount" -ForegroundColor Gray
    Write-Host "     Citations        : $hasCitations" -ForegroundColor Gray
    Write-Host "     Done event       : $hasDone" -ForegroundColor Gray
} else {
    Write-Host "  [FAIL] Query pipeline FAILED" -ForegroundColor Red
    Write-Host "     Tokens: $tokenCount | Citations: $hasCitations | Done: $hasDone" -ForegroundColor Red
}

# -----------------------------------------------------------------------------
# PHASE C - RATE LIMITING TEST
# -----------------------------------------------------------------------------

Write-Host "`n==========================================" -ForegroundColor Magenta
Write-Host "  PHASE C: Per-Workspace Rate Limiting" -ForegroundColor Magenta
Write-Host "==========================================" -ForegroundColor Magenta

# -----------------------------------------------------------------------------
# STEP 8 - Temporarily set rpm to 2
# -----------------------------------------------------------------------------
Write-Host "`n[ STEP 8 ] Setting workspace rate_limit_rpm = 2 for test..." -ForegroundColor Yellow

docker exec ragops_postgres psql -U postgres -d ragops -c `
    "UPDATE workspaces SET rate_limit_rpm = 2 WHERE id = '$WORKSPACE_ID';" | Out-Null

Write-Host "  [OK] rate_limit_rpm set to 2" -ForegroundColor Green

# -----------------------------------------------------------------------------
# STEP 9 - Flush Redis RPM counter
# -----------------------------------------------------------------------------
Write-Host "`n[ STEP 9 ] Flushing Redis rate limit counter..." -ForegroundColor Yellow

docker exec ragops_redis redis-cli DEL "rl:rpm:$WORKSPACE_ID" | Out-Null
Write-Host "  [OK] Redis counter cleared" -ForegroundColor Green

# -----------------------------------------------------------------------------
# STEP 10 - Fire 4 rapid requests, expect 429
# -----------------------------------------------------------------------------
Write-Host "`n[ STEP 10 ] Firing 4 rapid requests (expect 429 after 2)..." -ForegroundColor Yellow

$got429 = $false

for ($i = 1; $i -le 4; $i++) {
    try {
        $resp = Invoke-WebRequest `
            -Uri "$BASE/query" `
            -Method POST `
            -Headers $AUTH `
            -Body $queryBody `
            -ContentType "application/json" `
            -ErrorAction Stop

        Write-Host "  Request $i -> HTTP $($resp.StatusCode) [OK]" -ForegroundColor Gray

    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -eq 429) {
            $retryAfter = $_.Exception.Response.Headers["Retry-After"]
            Write-Host "  Request $i -> HTTP 429 [OK] (Retry-After: ${retryAfter}s)" -ForegroundColor Green
            $got429 = $true
        } else {
            Write-Host "  Request $i -> HTTP $code [WARN] (unexpected)" -ForegroundColor DarkYellow
        }
    }
}

if ($got429) {
    Write-Host "  [OK] Rate limiting PASSED - 429 fired correctly" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Rate limiting FAILED - no 429 received" -ForegroundColor Red
    Write-Host "     Check: require_rate_limit wired into query.py?" -ForegroundColor Gray
}

# -----------------------------------------------------------------------------
# STEP 11 - Restore rpm to default 60
# -----------------------------------------------------------------------------
Write-Host "`n[ STEP 11 ] Restoring rate_limit_rpm = 60..." -ForegroundColor Yellow

docker exec ragops_postgres psql -U postgres -d ragops -c `
    "UPDATE workspaces SET rate_limit_rpm = 60 WHERE id = '$WORKSPACE_ID';" | Out-Null

Write-Host "  [OK] Restored" -ForegroundColor Green

# -----------------------------------------------------------------------------
# FINAL SUMMARY
# -----------------------------------------------------------------------------
Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "  TEST SUMMARY" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  A - Ingestion + Celery + RAGAS   : check above" -ForegroundColor White
Write-Host "  B - Query + SSE + Rerank         : check above" -ForegroundColor White
Write-Host "  C - Rate limiting + 429          : check above" -ForegroundColor White
Write-Host "`n  If any step failed, run:" -ForegroundColor Gray
Write-Host "  docker-compose logs -f celery_worker backend`n" -ForegroundColor Gray