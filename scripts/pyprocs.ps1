# list python processes via Get-CimInstance (wmic removed on this host)
$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'"
$pat = $args[0]
if (-not $pat) { $pat = "adjudicate" }
$n = 0
foreach ($p in $procs) {
  if ($p.CommandLine -match $pat) {
    Write-Output ("PID " + $p.ProcessId + " :: " + $p.CommandLine.Substring(0, [Math]::Min(100, $p.CommandLine.Length)))
    $n++
  }
}
Write-Output ("MATCH " + $n)
