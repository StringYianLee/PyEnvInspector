# MSI 全流程验证脚本(需要管理员权限运行)
# 验证: 安装 1.0.0 -> 文件/快捷方式/ARP -> 启动冒烟 -> 升级 1.0.1 -> 卸载 -> 清理检查
$ErrorActionPreference = "Continue"
$root   = "C:\Users\Liyian\WorkBuddy\python-pkg\pyenv-inspector"
$logDir = "$root\build"
$out    = "$logDir\verify_result.txt"
$msi100 = "$logDir\PyEnvInspector-1.0.0.msi"
$msi101 = "$logDir\PyEnvInspector-1.0.1.msi"
$installDir = "$env:ProgramFiles\PyEnvInspector Project\PyEnv Inspector"
$exe = "$installDir\PyEnvInspector.exe"
$name = "PyEnv Inspector"

function Get-ARP {
    Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*" -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -eq $name } |
        Select-Object -First 1 DisplayName, DisplayVersion, PSChildName
}

Set-Content -Path $out -Value "== MSI 验证开始 $(Get-Date -Format 'HH:mm:ss') =="

# ---- 1) 安装 1.0.0 ----
$p = Start-Process msiexec -ArgumentList "/i", "`"$msi100`"", "/qn", "/l*v", "`"$logDir\v100.log`"" -Wait -PassThru
Add-Content $out "INSTALL_100_EXIT=$($p.ExitCode)"

# ---- 2) 验证安装结果 ----
Add-Content $out ("EXE_EXISTS=" + (Test-Path $exe))
Add-Content $out ("STARTMENU_LNK=" + (Test-Path "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\$name\$name.lnk"))
Add-Content $out ("DESKTOP_LNK=" + (Test-Path "$env:PUBLIC\Desktop\$name.lnk"))
$arp = Get-ARP
Add-Content $out ("ARP_VERSION=" + $arp.DisplayVersion)
Add-Content $out ("ARP_PRODUCTCODE=" + $arp.PSChildName)
Add-Content $out ("FILE_COUNT=" + (Get-ChildItem $installDir -Recurse -File -ErrorAction SilentlyContinue).Count)

# ---- 3) 启动冒烟 ----
if (Test-Path $exe) {
    Start-Process $exe
    Start-Sleep -Seconds 6
    $proc = Get-Process PyEnvInspector -ErrorAction SilentlyContinue
    Add-Content $out ("APP_RUNNING=" + ($null -ne $proc))
    if ($proc) { Stop-Process -Name PyEnvInspector -Force }
    Start-Sleep -Seconds 1
}

# ---- 4) 升级到 1.0.1(MajorUpgrade 自动卸旧装新) ----
$p2 = Start-Process msiexec -ArgumentList "/i", "`"$msi101`"", "/qn", "/l*v", "`"$logDir\v101.log`"" -Wait -PassThru
Add-Content $out "UPGRADE_101_EXIT=$($p2.ExitCode)"
$arp2 = Get-ARP
Add-Content $out ("ARP_VERSION_AFTER_UPGRADE=" + $arp2.DisplayVersion)
Add-Content $out ("EXE_AFTER_UPGRADE=" + (Test-Path $exe))

# ---- 5) 卸载 ----
if ($arp2.PSChildName) {
    $p3 = Start-Process msiexec -ArgumentList "/x", $arp2.PSChildName, "/qn", "/l*v", "`"$logDir\uninstall.log`"" -Wait -PassThru
    Add-Content $out "UNINSTALL_EXIT=$($p3.ExitCode)"
}
Add-Content $out ("EXE_AFTER_UNINSTALL=" + (Test-Path $exe))
Add-Content $out ("INSTALLDIR_AFTER_UNINSTALL=" + (Test-Path $installDir))
Add-Content $out ("STARTMENU_AFTER_UNINSTALL=" + (Test-Path "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\$name"))
Add-Content $out ("DESKTOP_AFTER_UNINSTALL=" + (Test-Path "$env:PUBLIC\Desktop\$name.lnk"))
$arp3 = Get-ARP
Add-Content $out ("ARP_AFTER_UNINSTALL=" + ($null -ne $arp3))
Add-Content $out "== 验证结束 =="
