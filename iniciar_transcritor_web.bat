@echo off
cd /d "%~dp0"
echo Abrindo Transcritor Web EN-PT...
echo.
python -m streamlit run transcritor_web.py
pause
