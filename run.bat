@echo off
REM Launch the EMG robot-arm reaching game.
REM Prefers a local .venv (see docs\QUICKSTART.md); otherwise activates the conda
REM env "env_emg-simulator". Extra args pass through, e.g.:  run.bat --auto
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto venv
goto conda

:venv
".venv\Scripts\python.exe" -m emg_sim.app %*
goto end

:conda
set "CONDA=%USERPROFILE%\anaconda3\Scripts\activate.bat"
if not exist "%CONDA%" set "CONDA=%USERPROFILE%\miniconda3\Scripts\activate.bat"
if not exist "%CONDA%" goto noenv
call "%CONDA%" env_emg-simulator
cd /d "%~dp0"
python -m emg_sim.app %*
goto end

:noenv
echo [run.bat] No .venv found and no Anaconda/Miniconda under %USERPROFILE%.
echo See docs\QUICKSTART.md to set up an environment first.
pause
exit /b 1

:end
if errorlevel 1 pause
