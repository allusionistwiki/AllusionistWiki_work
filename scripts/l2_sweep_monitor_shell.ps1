$targets = Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'bash.exe' -or $_.Name -eq 'sh.exe') -and ($_.CommandLine -match 'ADJUDICATE V2') }
foreach ($t in $targets) {
  Stop-Process -Id $t.ProcessId -Force -ErrorAction SilentlyContinue
  Write-Output ("killed " + $t.ProcessId)
}
Write-Output ("SWEEP-COUNT " + $targets.Count)
