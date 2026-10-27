@echo off
rem ============================================================
rem  PyEnv Inspector 启动脚本 (Windows)
rem  优先使用项目 .venv; 若不存在则使用系统 Python
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        py -3 main.py
    ) else (
        python main.py
    )
)
if errorlevel 1 pause
