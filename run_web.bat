@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONPATH=%~dp0"
echo 启动量化系统 Web 服务...
echo PYTHONPATH: %PYTHONPATH%
echo.
streamlit run web/app.py
pause