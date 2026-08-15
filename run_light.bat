@echo off
REM Lightweight launcher for weak / integrated-GPU machines: lighter (slower-scrolling)
REM waveforms and no MSAA -- the graph is kept, just cheaper to draw.
REM On a slow laptop, put THIS on the desktop instead of run.bat -- the operator just
REM double-clicks it, no arguments needed. It simply runs run.bat with --light.
call "%~dp0run.bat" --light %*
