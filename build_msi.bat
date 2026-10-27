@echo off
rem ============================================================
rem  PyEnv Inspector MSI 一键构建 (需先完成 docs/BUILD_MSI.md 环境准备)
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
python scripts\build_msi.py --version 1.0.0
pause
