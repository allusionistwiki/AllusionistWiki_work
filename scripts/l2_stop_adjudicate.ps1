$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'adjudicate_l2' }
foreach ($p in $procs) {
  Write-Output "KILL PID $($p.ProcessId)"
  Stop-Process -Id $p.ProcessId -Force
}
Start-Sleep -Seconds 2
$after = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'adjudicate_l2' }
Write-Output "REMAINING $(@($after).Count)"
