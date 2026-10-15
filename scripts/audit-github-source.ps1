param([switch]$Strict)
$ErrorActionPreference = 'Stop'
$root = (git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Not a Git repository.' }
Push-Location $root
try {
  $tracked = @(git ls-files)
  $modified = @(git ls-files -m)
  $untracked = @(git ls-files --others --exclude-standard)
  $sourcePattern = '^(daemon|renderer|electron|installer|scripts|shared|\.github)/.*\.(py|ts|tsx|js|mjs|cjs|ps1|yml|yaml|json)$'
  $source = @($untracked | Where-Object { $_ -match $sourcePattern })
  $branch = (git branch --show-current).Trim()
  $remote = (git remote get-url origin).Trim()
  $head = (git rev-parse --short HEAD).Trim()
  $ahead = 0
  $behind = 0
  git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) {
    $counts = ((git rev-list --left-right --count '@{upstream}...HEAD').Trim() -split '\s+')
    $behind = [int]$counts[0]; $ahead = [int]$counts[1]
  }
  [pscustomobject]@{ repository=$remote; branch=$branch; head=$head; tracked=$tracked.Count; modified=$modified.Count; untracked=$untracked.Count; untracked_source=$source.Count; ahead=$ahead; behind=$behind; source_sample=@($source | Select-Object -First 20) } | ConvertTo-Json -Depth 4
  if ($Strict -and ($modified.Count -gt 0 -or $source.Count -gt 0 -or $ahead -gt 0)) { exit 2 }
} finally { Pop-Location }
