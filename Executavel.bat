@echo off
setlocal
cd /d "%~dp0"
echo CustoClaro - Preparando aplicativo...
if exist ".venv\Scripts\python.exe" goto dependencies
py -3 -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if errorlevel 1 goto pythonfallback
py -3 -m venv .venv
if errorlevel 1 goto failed
goto dependencies
:pythonfallback
python -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if errorlevel 1 goto missingpython
python -m venv .venv
if errorlevel 1 goto failed
:dependencies
if not exist ".venv\requirements.installed" goto install
fc /b requirements.txt .venv\requirements.installed >nul 2>&1
if not errorlevel 1 goto launch
:install
echo Instalando dependencias. A primeira abertura precisa de internet...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
copy /y requirements.txt .venv\requirements.installed >nul
:launch
".venv\Scripts\python.exe" launcher.py
if errorlevel 1 goto failed
exit /b 0
:missingpython
echo Instale Python 3.10 ou superior em https://www.python.org/downloads/
echo Marque Add Python to PATH e execute este arquivo novamente.
pause
exit /b 1
:failed
echo Nao foi possivel concluir. Veja o erro acima e tente novamente.
pause
exit /b 1
