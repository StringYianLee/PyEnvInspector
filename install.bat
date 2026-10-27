@echo off
rem ============================================================
rem  PyEnv Inspector 一键安装脚本 (Windows)
rem  作用: 在项目目录创建 .venv 虚拟环境并安装依赖
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

echo [1/3] 创建虚拟环境 .venv ...
if exist ".venv\Scripts\python.exe" (
    echo      已存在, 跳过创建
) else (
    py -3 -m venv .venv
    if errorlevel 1 (
        echo      未找到 py 启动器, 尝试 python ...
        python -m venv .venv
        if errorlevel 1 (
            echo [错误] 未检测到 Python 3.8+, 请先安装 Python。
            pause
            exit /b 1
        )
    )
)

echo [2/3] 安装依赖 (PySide6 / packaging) ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败, 请检查网络或换用国内镜像:
    echo        ".venv\Scripts\python.exe" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    pause
    exit /b 1
)

echo [3/3] 安装完成!
echo.
echo 运行方式: 双击 run.bat 或执行  .venv\Scripts\python.exe main.py
pause
