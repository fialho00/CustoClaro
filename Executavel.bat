@echo off
setlocal
cd /d "%~dp0"
echo WattCola - Preparando aplicativo...
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
if not errorlevel 1 goto webdependencies
:install
echo Instalando dependencias. A primeira abertura precisa de internet...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
copy /y requirements.txt .venv\requirements.installed >nul
:webdependencies
if exist "dist\index.html" goto launch
where npm.cmd >nul 2>&1
if errorlevel 1 goto missingnode
if not exist "node_modules\vite\bin\vite.js" goto npminstall
if not exist ".venv\package-lock.installed" goto npminstall
fc /b package-lock.json .venv\package-lock.installed >nul 2>&1
if not errorlevel 1 goto webbuild
:npminstall
echo Preparando interface visual...
call npm.cmd ci --no-audit --no-fund
if errorlevel 1 goto failed
copy /y package-lock.json .venv\package-lock.installed >nul
:webbuild
echo Atualizando a interface...
call npm.cmd run build
if errorlevel 1 goto failed
:launch
".venv\Scripts\python.exe" launcher.py
if errorlevel 1 goto failed
exit /b 0
:missingnode
echo A interface compilada nao foi encontrada. Instale Node.js LTS em https://nodejs.org/
pause
exit /b 1
:missingpython
echo Instale Python 3.10 ou superior em https://www.python.org/downloads/
echo Marque Add Python to PATH e execute este arquivo novamente.
pause
exit /b 1
:failed
echo Nao foi possivel concluir. Veja o erro acima e tente novamente.
pause
exit /b 1
