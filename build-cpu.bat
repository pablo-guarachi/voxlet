@echo off
REM Build <APP_ID>.exe (APP_ID read from config.py) CPU-only variant (small/cpu/int8) with PyInstaller.
REM Run with the venv activated (.venv\Scripts\activate first).
REM
REM Differences from build.bat:
REM  - config.py is patched temporarily (small/cpu/int8) and ALWAYS restored
REM  - no CUDA DLLs bundled (cublas/cudnn are not needed on CPU)
REM
REM Output: dist\<APP_ID>\<APP_ID>.exe (onedir mode)

setlocal
cd /d "%~dp0"

if not exist .venv (
    echo ERROR: venv not found. Create it with: python -m venv .venv ^&^& .venv\Scripts\activate ^&^& pip install -r requirements.txt
    exit /b 1
)

call .venv\Scripts\activate.bat

REM Product name: single source = config.py (APP_ID derived from APP_NAME)
set APP_ID=
for /f "usebackq delims=" %%N in (`python -c "import config; print(config.APP_ID)"`) do set APP_ID=%%N
if "%APP_ID%"=="" (
    echo ERROR: could not read APP_ID from config.py
    exit /b 1
)
echo === App: %APP_ID% ===

echo === Backing up and patching config.py (CPU: small/cpu/int8) ===
copy /y config.py config.py.gpu-backup >nul
python -c "import re; p='config.py'; s=open(p,encoding='utf-8').read(); s=re.sub(r'(?m)^WHISPER_MODEL\s*=.*$', 'WHISPER_MODEL = \"small\"', s); s=re.sub(r'(?m)^WHISPER_DEVICE\s*=.*$', 'WHISPER_DEVICE = \"cpu\"', s); s=re.sub(r'(?m)^WHISPER_COMPUTE\s*=.*$', 'WHISPER_COMPUTE = \"int8\"', s); open(p,'w',encoding='utf-8',newline='').write(s)"
if errorlevel 1 (
    echo ERROR: config.py patch failed
    copy /y config.py.gpu-backup config.py >nul
    del /q config.py.gpu-backup
    exit /b 1
)

echo === Cleaning previous build ===
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist %APP_ID%.spec del /q %APP_ID%.spec

echo === Building CPU variant with PyInstaller ===
pyinstaller ^
    --name %APP_ID% ^
    --windowed ^
    --icon icons\app.ico ^
    --add-data "icons;icons" ^
    --add-data "assets;assets" ^
    --add-data "theme.qss;." ^
    --collect-all faster_whisper ^
    --collect-all ctranslate2 ^
    --collect-all sounddevice ^
    --collect-all PySide6 ^
    --collect-all pycaw ^
    --collect-all comtypes ^
    --collect-all onnxruntime ^
    app.py
set BUILD_RC=%errorlevel%

echo === Restoring original config.py ===
copy /y config.py.gpu-backup config.py >nul
del /q config.py.gpu-backup

if not "%BUILD_RC%"=="0" (
    echo === CPU BUILD FAILED ===
    exit /b 1
)

echo.
echo === CPU BUILD OK ===
echo Executable: dist\%APP_ID%\%APP_ID%.exe
echo.
echo Note:
echo  - Model: small on CPU int8 - the first run downloads ~460MB to %%USERPROFILE%%\.cache\huggingface
echo  - The executable is not signed: Windows SmartScreen may warn on first launch
endlocal
