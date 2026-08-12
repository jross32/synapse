# Contract-in-prompt A/B: the same piece built twice, differing only in whether the
# signatures it will be graded against are stated before it writes anything.
# Sequential on purpose - two 7B generations at once on a 6 GB card would measure
# contention rather than prompts.
$py = "C:\Users\justi\AppData\Local\Programs\Python\Python312\python.exe"
$root = "C:\Users\justi\synapse"
Set-Location $root

Write-Output "=== arm A: baseline (contract withheld) ==="
& $py "$root\benchmarks\app-build\probe_storage_repairs.py" 2>&1 |
    Out-File -FilePath "$root\data\ab-baseline.log" -Encoding utf8
Get-Content "$root\data\ab-baseline.log" | Select-Object -Last 8

Write-Output ""
Write-Output "=== arm B: contract stated up front ==="
& $py "$root\benchmarks\app-build\probe_storage_repairs.py" --with-contract 2>&1 |
    Out-File -FilePath "$root\data\ab-contract.log" -Encoding utf8
Get-Content "$root\data\ab-contract.log" | Select-Object -Last 8

Write-Output ""
Write-Output "=== done ==="
