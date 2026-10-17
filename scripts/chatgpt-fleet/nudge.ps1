# One cheap supervisor pass: nudge every idle owned worker (not DONE), print one line per lane.
param([string]$Config = (Join-Path $PSScriptRoot 'config.json'))
$s = $PSScriptRoot
$cfg = Get-Content $Config -Raw | ConvertFrom-Json
$chats = Get-Content $cfg.chatsFile | Where-Object { $_ -match '/c/' } | ForEach-Object { $k,$u = $_.Split('|'); [pscustomobject]@{ lane=$k; id=($u -split '/c/')[1] } }
$ids = @($chats | ForEach-Object { $_.id })
$js = (Get-Content "$s\gen.js" -Raw).Replace('OWNED_IDS', (ConvertTo-Json -InputObject $ids -Compress))
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("synapse-fleet-gen-" + [guid]::NewGuid().ToString('N') + ".js")
[System.IO.File]::WriteAllText($tmp, $js)
try { $g = ((& "$s\pw.ps1" -CodeFile $tmp -Config $Config) -join "`n") } finally { Remove-Item $tmp -ErrorAction SilentlyContinue }; $g = $g -split '\n|\n'
foreach($c in $chats){
  $id8 = $c.id.Substring(0,8)
  $line = $g | Where-Object { $_ -match $id8 } | Select-Object -First 1
  $state = if(-not $line){'notab'} elseif($line -match 'gen=[1-9]'){'busy'} elseif($line -match 'next:\s*DONE'){'done'} else {'idle'}
  $sha = [regex]::Match([string]$line,'commit:\s*([0-9a-f]{7})').Groups[1].Value
  if($state -eq 'idle'){
    $pf = if($c.lane -eq 'integration'){"$s\continue-integrator.txt"}else{"$s\continue-worker.txt"}
    $r = & "$s\followup.ps1" -ChatId $c.id -PromptFile $pf -Config $Config 2>&1 | Out-String
    $state += '->' + ([regex]::Match($r,'sent\W+\w+|error[^,}]{0,60}').Value)
  }
  "$($c.lane) $id8 $state $sha"
}