@echo off
cd /d "%~dp0"
echo Job Radar tracker: opening http://127.0.0.1:8770 ...
".venv\Scripts\python.exe" -m pipeline tracker
pause
