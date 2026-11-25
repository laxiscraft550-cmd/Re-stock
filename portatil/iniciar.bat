@echo off
cd /d "%~dp0"
set PYTHONHOME=
set PYTHONPATH=
set PYTHONNOUSERSITE=1
if not exist .env echo Primero abre 1-pasar_a_usb.bat en la PC de casa.& pause & exit /b
echo No cierres esta ventana ni retires el USB mientras el bot este encendido.
echo Para apagarlo: Ctrl+C o cierra la ventana.
python\python.exe bot.py
pause
