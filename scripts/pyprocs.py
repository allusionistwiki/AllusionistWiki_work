# list python processes whose CommandLine matches a regex, print pid
import subprocess, sys, re
pat = sys.argv[1] if len(sys.argv) > 1 else "adjudicate"
out = subprocess.run(["wmic", "process", "where", "name='python.exe'",
                      "get", "ProcessId,CommandLine", "/format:csv"],
                     capture_output=True, text=True).stdout
n = 0
for line in out.splitlines():
    if "ProcessId" in line and "CommandLine" in line:
        continue
    m = re.search(r"([^,]*%s[^,]*),(\d+)\s*$" % re.escape(pat), line)
    if m:
        print("PID", m.group(2), m.group(1)[:80])
        n += 1
print("MATCH", n)
