<#
Creates (or removes with -Uninstall) two .lnk shortcuts for the laptop variant:
  1. User Desktop - manual launch with a double click
  2. Windows Startup folder - autostart at login

The shortcuts point straight at the venv's pythonw.exe (no console window).
Idempotent: re-running overwrites without errors.
#>
[CmdletBinding()]
param(
  [switch]$Uninstall
)

$here        = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $here
$pythonw     = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
$entry       = Join-Path $here "run_laptop.py"
$icon        = Join-Path $projectRoot "icons\app.ico"

# Product name: single source = config.py (APP_NAME)
$python  = Join-Path $projectRoot ".venv\Scripts\python.exe"
$appName = $null
if (Test-Path $python) {
  $appName = & $python -c "import sys; sys.path.insert(0, r'$projectRoot'); import config; print(config.APP_NAME)" 2>$null
}
if (-not $appName) { $appName = "Voxlet" }

$desktop = [Environment]::GetFolderPath("Desktop")
$startup = [Environment]::GetFolderPath("Startup")
$shortcuts = @(
  @{ Path = Join-Path $desktop "$appName (Laptop).lnk"; Where = "Desktop" },
  @{ Path = Join-Path $startup "$appName (Laptop).lnk"; Where = "Startup (autostart)" }
)
# Shortcuts created under the project's previous name: removed to avoid a double autostart
$legacyNames = @("WhisperFlow Clone (Laptop).lnk")
foreach ($n in $legacyNames) {
  if ($n -eq "$appName (Laptop).lnk") { continue }
  foreach ($dir in @($desktop, $startup)) {
    $old = Join-Path $dir $n
    if (Test-Path $old) {
      Remove-Item $old -Force
      Write-Output ("  - Removed legacy shortcut: {0}" -f $old)
    }
  }
}

if ($Uninstall) {
  Write-Output "=== Removing shortcuts ==="
  foreach ($s in $shortcuts) {
    if (Test-Path $s.Path) {
      Remove-Item $s.Path -Force
      Write-Output ("  - Removed: {0}" -f $s.Where)
    } else {
      Write-Output ("  - Skip:    {0} (not present)" -f $s.Where)
    }
  }
  exit 0
}

if (-not (Test-Path $pythonw)) {
  Write-Error "pythonw.exe not found at $pythonw - run 'pip install -r requirements.txt' in the project venv first"
  exit 1
}
if (-not (Test-Path $entry)) {
  Write-Error "run_laptop.py not found at $entry"
  exit 1
}

Write-Output "=== Creating shortcuts ==="
Write-Output "  Target:    $pythonw"
Write-Output "  Arguments: $entry"
Write-Output "  Workdir:   $projectRoot"
Write-Output ""

$wsh = New-Object -ComObject WScript.Shell
foreach ($s in $shortcuts) {
  $sc = $wsh.CreateShortcut($s.Path)
  $sc.TargetPath       = $pythonw
  $sc.Arguments        = "`"$entry`""
  $sc.WorkingDirectory = $projectRoot
  $sc.WindowStyle      = 7
  if (Test-Path $icon) { $sc.IconLocation = $icon }
  $sc.Description      = "$appName (CPU-only laptop variant)"
  $sc.Save()
  Write-Output ("  + Created: {0}" -f $s.Where)
}

Write-Output ""
Write-Output "Done."
Write-Output " - Double-click the Desktop icon to launch manually"
Write-Output " - The app starts automatically at the next Windows login"
Write-Output ""
Write-Output "To remove the shortcuts: re-run this script with the -Uninstall flag"
