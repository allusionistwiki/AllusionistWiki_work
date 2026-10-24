# L2 adjudicate launcher: 3 shards, windowed windows (no -WindowStyle Hidden), detached
$repo = "C:\Users\d5dx\Downloads\Code\AllusionistWiki_work"
$py = (Get-Command python).Source
& $py -c "import openai" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Output "FATAL: python without openai: $py"; exit 1 }
Write-Output "PY=$py"
for ($i = 0; $i -lt 3; $i++) {
  $p = Start-Process -FilePath $py -ArgumentList "scripts/adjudicate_l2.py 20261024T1608_fc8d --shard $i/3" -WorkingDirectory $repo -PassThru
  Write-Output "SHARD $i PID $($p.Id)"
}
