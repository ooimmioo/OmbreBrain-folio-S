@echo off
cd /d "%~dp0"
python tools\accept_episode.py --open
echo.
echo Report opened in your browser. You can close this window after reading the result.
pause
