@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 启动量化系统桌面客户端...
echo.
python -m desktop.main
if errorlevel 1 pause