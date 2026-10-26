# Watch the v2 log for a TRUE DONE (baseline: count DONE lines at start; alert only on increase)
$LOG = "data/adjudicate_v2_20261024T1608_fc8d.log"
$base = (Select-String -Path $LOG -Pattern "=== L2 ADJUDICATE V2 DONE" -AllMatches).Matches.Count
Write-Output ("monitor4 baseline=" + $base)
while ($true) {
  Start-Sleep -Seconds 1800
  $n = (Select-String -Path $LOG -Pattern "=== L2 ADJUDICATE V2 DONE" -AllMatches).Matches.Count
  $last = Get-Content $LOG -Tail 1
  Write-Output ("V2PROG $last")
  if ($n -gt $base) { Write-Output "L2-ADJ-V2-DONE-TRUE"; exit 0 }
}
