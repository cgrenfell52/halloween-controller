@echo off
setlocal
cd /d "%~dp0.."
set HALLOWEEN_AUDIO_DISABLED=1
set HALLOWEEN_USE_MOCK_ARDUINO=1
set HALLOWEEN_MOCK_SCENE_DELAY_SCALE=0
set PYTHON_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
if exist "%PYTHON_EXE%" (
  "%PYTHON_EXE%" app.py
) else (
  python app.py
)
