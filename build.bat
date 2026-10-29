@echo off
cd /d "%~dp0"
py -m pip install --upgrade -r requirements-dev.txt || exit /b 1
py -m unittest || exit /b 1
py -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name DiagnosticoEquipos ^
  --icon assets\icon.ico ^
  --add-data "diagnostico\collect.ps1;diagnostico" ^
  --add-data "diagnostico\demo.json;diagnostico" ^
  --add-data "assets\icon.ico;assets" ^
  main.py || exit /b 1
echo.
echo Ejecutable generado en dist\DiagnosticoEquipos.exe
