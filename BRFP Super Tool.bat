@echo off
setlocal EnableExtensions
title BRFP Super Tool
cd /d "%~dp0"
set "RT=%~dp0runtime\python\python.exe"
if exist "%RT%" goto :rodar

rem ---- primeira vez neste computador: o Super Tool usa um Python proprio (runtime\python)
rem      BRFP_BAIXAR=1, 2 ou 3 responde a pergunta abaixo sem esperar (instalacao automatica)
set "OPCAO=%BRFP_BAIXAR%"
if defined OPCAO goto :opcao
echo.
echo  ===================================================================
echo    BRFP Super Tool - primeira vez neste computador
echo  ===================================================================
echo.
echo    O Super Tool usa um Python proprio, que fica dentro desta pasta
echo    (runtime\python). Nada e instalado no Windows.
echo.
echo    [1] Baixar o Python agora (11 MB, de python.org).
echo        Os pacotes do Conversor de Faces e do Criador de Minifaces
echo        sao baixados quando voce abrir essas ferramentas.
echo    [2] Baixar o Python e todos os pacotes agora (cerca de 110 MB).
echo    [3] Nao baixar: usar o Python que ja esta instalado no computador.
echo.
choice /c 123 /n /m "   Escolha 1, 2 ou 3: "
set "OPCAO=%errorlevel%"
:opcao
if "%OPCAO%"=="3" goto :sistema
set "EXTRA="
if "%OPCAO%"=="2" set "EXTRA=-Pacotes"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0comum\instalar_python.ps1" %EXTRA%
if exist "%RT%" goto :rodar
echo.
echo  Nao foi possivel baixar o Python agora. Procurando um Python instalado no computador...

:sistema
set "PY="
for %%P in (python py) do if not defined PY call :testar %%P
if not defined PY (
  echo.
  echo  Nenhum Python 3.10 ou mais novo foi encontrado neste computador.
  echo  Abra este arquivo de novo e escolha [1] para baixar o Python do Super Tool
  echo  ^(precisa de internet so na primeira vez^).
  echo.
  pause
  exit /b 1
)
%PY% supertool.py %*
if errorlevel 1 pause
exit /b

:testar
%1 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=%1"
exit /b

:rodar
"%RT%" -X utf8 supertool.py %*
if errorlevel 1 pause
