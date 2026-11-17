@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=
where py >nul 2>nul && set PY=py
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY goto nopy
echo [1/3] Preparation de l'environnement...
if not exist venv\Scripts\activate.bat %PY% -m venv venv
call venv\Scripts\activate.bat
echo [2/3] Installation de Flask...
pip install -q -r requirements-local.txt
if errorlevel 1 goto err
echo [3/3] Demarrage du site (le navigateur s'ouvre tout seul)...
python app.py
pause
exit /b
:nopy
echo Python n'est pas installe.
echo Telechargez-le sur https://www.python.org/downloads/ et COCHEZ "Add python.exe to PATH" a l'installation.
pause
exit /b
:err
echo Erreur pendant l'installation de Flask. Verifiez votre connexion Internet et relancez.
pause
