@echo off
cd /d "%~dp0"
if not defined PYTHON set PYTHON=py
%PYTHON% -m pip install --upgrade -r requirements-dev.txt || exit /b 1
%PYTHON% -m unittest || exit /b 1
%PYTHON% -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name DiagnosticoEquipos ^
  --icon assets\icon.ico ^
  --add-data "diagnostico\collect.ps1;diagnostico" ^
  --add-data "diagnostico\demo.json;diagnostico" ^
  --add-data "assets\icon.ico;assets" ^
  main.py || exit /b 1
echo.
echo Ejecutable generado en dist\DiagnosticoEquipos.exe