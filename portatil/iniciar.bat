@echo off
cd /d "%~dp0"
set PYTHONHOME=
set PYTHONPATH=
set PYTHONNOUSERSITE=1
echo Para apagar el bot cierra esta ventana.
python\python.exe bot.py
pause
