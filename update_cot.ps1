$logFile = "$PSScriptRoot\cot_update.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

try {
    $result = Invoke-RestMethod -Method POST "http://localhost:8010/api/collect/trigger?series=cot" -TimeoutSec 60
    $rows = $result.cot.rows
    $status = $result.cot.status
    $msg = "[$timestamp] OK - rows=$rows status=$status"
    if ($result.cot.errors.Count -gt 0) {
        $errs = $result.cot.errors -join '; '
        $msg += " errors=$errs"
    }
} catch {
    $err = $_.ToString()
    $msg = "[$timestamp] ERRO - $err"
}

Add-Content -Path $logFile -Value $msg -Encoding UTF8
