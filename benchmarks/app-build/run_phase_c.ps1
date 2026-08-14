# The Phase C gate. Sequential - two 7B generations at once on a 6 GB card would measure
# contention rather than prompts.
$py = "C:\Users\justi\AppData\Local\Programs\Python\Python312\python.exe"
$root = "C:\Users\justi\synapse"
Set-Location $root

foreach ($variant in @("baseline", "both", "split", "deepseek")) {
    Write-Output "########## $variant ##########"
    & $py "$root\benchmarks\app-build\phase_c_batch.py" $variant 4 2>&1 |
        Tee-Object -FilePath "$root\data\phase-c-$variant.log"
    Write-Output ""
}
Write-Output "########## sweep complete ##########"
