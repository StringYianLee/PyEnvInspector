# MSI perUser 全流程验证脚本(免管理员)
$ErrorActionPreference = "Continue"
$root   = "C:\Users\Liyian\WorkBuddy\python-pkg\pyenv-inspector"
$logDir = "$root\build"
$out    = "$logDir\verify_user_result.txt"
$msi100 = "$logDir\PyEnvInspector-1.1.0-user.msi"
$msi101 = "$logDir\PyEnvInspector-1.1.1-user.msi"
$installDir = "$env:LOCALAPPDATA\PyEnvInspector Project\PyEnv Inspector"
$exe = "$installDir\PyEnvInspector.exe"
$name = "PyEnv Inspector"

function Get-ARP {
    Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
                     "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*" -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -eq $name } |
        Select-Object -First 1 DisplayName, DisplayVersion, PSChildName
}

Set-Content -Path $out -Value "== perUser MSI 验证开始 $(Get-Date -Format 'HH:mm:ss') =="

# ---- 1) 安装 1.0.0 ----
$p = Start-Process msiexec -ArgumentList "/i", "`"$msi100`"", "/qn", "/l*v", "`"$logDir\v100u.log`"" -Wait -PassThru
Add-Content $out "INSTALL_100_EXIT=$($p.ExitCode)"

# ---- 2) 验证安装 ----
Add-Content $out ("EXE_EXISTS=" + (Test-Path $exe))
Add-Content $out ("FILE_COUNT=" + (Get-ChildItem $installDir -Recurse -File -ErrorAction SilentlyContinue).Count)
Add-Content $out ("STARTMENU_LNK=" + (Test-Path "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\$name\$name.lnk"))
Add-Content $out ("DESKTOP_LNK=" + (Test-Path "$([Environment]::GetFolderPath('Desktop'))\$name.lnk"))
Add-Content $out ("UNINSTALL_LNK=" + (Test-Path "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\$name\卸载 $name.lnk"))
$arp = Get-ARP
Add-Content $out ("ARP_VERSION=" + $arp.DisplayVersion)
Add-Content $out ("ARP_PRODUCTCODE=" + $arp.PSChildName)

# ---- 3) 启动冒烟 ----
if (Test-Path $exe) {
    Start-Process $exe
    Start-Sleep -Seconds 6
    $proc = Get-Process PyEnvInspector -ErrorAction SilentlyContinue
    Add-Content $out ("APP_RUNNING=" + ($null -ne $proc))
    if ($proc) { Stop-Process -Name PyEnvInspector -Force }
    Start-Sleep -Seconds 1
}

# ---- 4) 升级 1.0.1 ----
$p2 = Start-Process msiexec -ArgumentList "/i", "`"$msi101`"", "/qn", "/l*v", "`"$logDir\v101u.log`"" -Wait -PassThru
Add-Content $out "UPGRADE_101_EXIT=$($p2.ExitCode)"
$arp2 = Get-ARP
Add-Content $out ("ARP_VERSION_AFTER_UPGRADE=" + $arp2.DisplayVersion)
Add-Content $out ("EXE_AFTER_UPGRADE=" + (Test-Path $exe))

# ---- 5) 卸载 ----
if ($arp2.PSChildName) {
    $p3 = Start-Process msiexec -ArgumentList "/x", $arp2.PSChildName, "/qn", "/l*v", "`"$logDir\uninstallu.log`"" -Wait -PassThru
    Add-Content $out "UNINSTALL_EXIT=$($p3.ExitCode)"
}
Add-Content $out ("EXE_AFTER_UNINSTALL=" + (Test-Path $exe))
Add-Content $out ("INSTALLDIR_AFTER_UNINSTALL=" + (Test-Path $installDir))
Add-Content $out ("STARTMENU_AFTER_UNINSTALL=" + (Test-Path "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\$name"))
Add-Content $out ("DESKTOP_AFTER_UNINSTALL=" + (Test-Path "$([Environment]::GetFolderPath('Desktop'))\$name.lnk"))
$arp3 = Get-ARP
Add-Content $out ("ARP_AFTER_UNINSTALL=" + ($null -ne $arp3))
Add-Content $out "== 验证结束 =="
