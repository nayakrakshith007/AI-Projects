@echo off
rem Job Radar V3, one click: starts the progress page (hidden), starts a full run (fast sources and job boards, about 40 minutes), opens the page.
rem The dashboard is a tab link on that page. This window closes by itself; the run keeps going without it.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m radar3 tracker --launch
