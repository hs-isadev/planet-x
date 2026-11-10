param([string]$Repository = '')
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot
$account = gh api user --jq .login
if ($LASTEXITCODE -ne 0) { throw 'GitHub could not be reached or authentication failed. No repository was changed.' }
if (-not $Repository) { $Repository = "$account/planet-x" }
if ($Repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') { throw 'Use an owner/repository name.' }
git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) {
    git init -b main
    if ($LASTEXITCODE -ne 0) { throw 'Could not initialize the source repository.' }
}
git rev-parse --verify --quiet HEAD | Out-Null
if ($LASTEXITCODE -ne 0) {
    git add --all
    if ($LASTEXITCODE -ne 0) { throw 'Could not stage the source. Check repository write access.' }
    git commit -m 'Complete temporal review and optional 3D observatory fixes'
    if ($LASTEXITCODE -ne 0) { throw 'Could not commit the source. Check Git identity and repository write access.' }
    git branch -M main
    if ($LASTEXITCODE -ne 0) { throw 'Could not select the source branch.' }
} elseif (git status --porcelain --untracked-files=normal) {
    git add --all
    if ($LASTEXITCODE -ne 0) { throw 'Could not stage the updated source.' }
    git commit -m 'Update Planet X observatory source'
    if ($LASTEXITCODE -ne 0) { throw 'Could not commit the updated source.' }
}
$ErrorActionPreference = 'Continue'
$existing = gh repo view $Repository --json nameWithOwner 2>$null
$repoExists = $LASTEXITCODE -eq 0
$ErrorActionPreference = 'Stop'
if ($LASTEXITCODE -eq 0) {
    $remoteUrl = "https://github.com/$Repository.git"
    $origin = $null
    if ((git remote) -contains 'origin') { $origin = git remote get-url origin }
    if ($origin -and $origin -ne $remoteUrl) { throw 'Origin already points elsewhere. Review that remote before uploading.' }
    if (-not $origin) { git remote add origin $remoteUrl; if ($LASTEXITCODE -ne 0) { throw 'Could not add the remote.' } }
    # Preserve remote history; upload this source snapshot on a new branch.
    $branch = 'codex/observatory-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
    git push origin "HEAD:refs/heads/$branch"
    if ($LASTEXITCODE -ne 0) { throw 'Upload failed; the local commit is intact.' }
    Write-Output "Uploaded: https://github.com/$Repository/tree/$branch"
} else {
    gh repo create $Repository --private --source $projectRoot --remote origin --push
    if ($LASTEXITCODE -ne 0) { throw 'Could not create/upload the repository. No force push was attempted.' }
    Write-Output "Uploaded: https://github.com/$Repository"
}



