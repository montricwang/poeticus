# Install a stable, user-local copy so the Desktop shortcut survives Git worktree removal.
$ErrorActionPreference = 'Stop'
$InstallDir = Join-Path $env:LOCALAPPDATA 'Poeticus\ControlCenter'
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
$Files = @('supervisor.py','server.py','index.html','app.js','style.css','favicon.svg','start-console.cmd','settings.example.json','README.md')
foreach ($File in $Files) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $File) -Destination (Join-Path $InstallDir $File) -Force
}
$LocalSettings = Join-Path $PSScriptRoot 'settings.local.json'
if (Test-Path -LiteralPath $LocalSettings) {
    Copy-Item -LiteralPath $LocalSettings -Destination (Join-Path $InstallDir 'settings.local.json') -Force
}
$Desktop = [Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $Desktop 'Poeticus Control.lnk'
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = Join-Path $InstallDir 'start-console.cmd'
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Description = 'Poeticus local development service console'
$Shortcut.Save()
Write-Host ('已安装本地控制台：' + $InstallDir)
Write-Host ('桌面快捷方式：' + $ShortcutPath)
Write-Host '双击快捷方式启动；不会自动启动七项服务。'
