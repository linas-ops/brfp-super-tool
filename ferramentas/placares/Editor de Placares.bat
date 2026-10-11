@echo off
title Editor de Placares FC
cd /d "%~dp0"
set PY=
if exist "%~dp0..\..\runtime\python\python.exe" set PY="%~dp0..\..\runtime\python\python.exe" -X utf8
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY (
  where py >nul 2>nul && set PY=py -3
)
if not defined PY (
  echo Python nao encontrado. Abra o "BRFP Super Tool.bat" uma vez para baixar o Python do Super Tool,
  echo ou instale o Python 3.10 ou mais novo em https://www.python.org/downloads/
  pause
  exit /b 1
)
%PY% servidor.py %*
if errorlevel 1 pause
