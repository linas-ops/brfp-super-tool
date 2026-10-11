@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set "PY=py -3.12"
if exist "%~dp0..\..\..\runtime\python\python.exe" set PY="%~dp0..\..\..\runtime\python\python.exe" -X utf8
if "%~1"=="" (
  echo Arraste arquivos .fbx de cabeca ou pastas de faces para este arquivo.
  echo Mais opcoes: Converter faces.bat --help
  pause
  exit /b
)
%PY% "%~dp0converter_faces.py" %*
pause
