@echo off
cd /d "%~dp0"
py -m pip install -r requirements.txt >nul 2>nul
py src\war2_remastered_table_editor.py
if errorlevel 1 pause
