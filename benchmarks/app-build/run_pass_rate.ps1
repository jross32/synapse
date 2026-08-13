# How often does the storage piece pass, not whether it can.
# One pass is a proof of possibility. Local models are noisy and free, so the honest
# follow-up is to repeat the identical run and report the rate.
$py = "C:\Users\justi\AppData\Local\Programs\Python\Python312\python.exe"
$root = "C:\Users\justi\synapse"
Set-Location $root

for ($i = 1; $i -le 4; $i++) {
    Write-Output "=== run $i of 4 ==="
    Remove-Item -Recurse -Force "$root\benchmarks\app-build\probe-storage-contract" -ErrorAction SilentlyContinue
    & $py "$root\benchmarks\app-build\probe_storage_repairs.py" --with-contract 2>&1 |
        Out-File -FilePath "$root\data\pass-rate-$i.log" -Encoding utf8
    Get-Content "$root\data\pass-rate-$i.log" | Select-String "passed=|verdict:" |
        ForEach-Object { "  $($_.Line.Trim())" }
}

Write-Output ""
Write-Output "=== summary ==="
$passes = 0
for ($i = 1; $i -le 4; $i++) {
    $line = (Get-Content "$root\data\pass-rate-$i.log" | Select-String "passed=True")
    if ($line) { $passes++ }
}
Write-Output "storage passed $passes of 4 runs"
