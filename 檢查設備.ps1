$ErrorActionPreference = 'Continue'
Write-Output '=== CPU ==='
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors
Write-Output '=== RAM GB ==='
[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
Write-Output '=== GPU ==='
Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
}
Write-Output '=== Free disk GB ==='
Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object DeviceID, @{N='FreeGB';E={[math]::Round($_.FreeSpace/1GB,1)}}
Write-Output '=== Ollama ==='
if (Get-Command ollama -ErrorAction SilentlyContinue) { ollama --version; ollama list }
else { Write-Output 'Ollama is not installed or is not on PATH.' }
Write-Output 'No serial numbers, user names, tokens, or network addresses collected. Nothing uploaded.'
Read-Host 'Press Enter to close'
