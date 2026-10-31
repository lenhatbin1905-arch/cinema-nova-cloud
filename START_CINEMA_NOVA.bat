@echo off
setlocal
cd /d "%~dp0"
echo ========================================
echo   CINEMA NOVA - Kiem tra khoi dong
echo ========================================
where py >nul 2>nul
if errorlevel 1 (
  echo Khong tim thay Python Launcher (py). Cai Python 3.11 tro len tu python.org, sau do mo lai tep nay.
  pause
  exit /b 1
)
py -3 -c "import sys; print('Python', sys.version.split()[0])"
if errorlevel 1 (
  echo Khong the chay Python. Can Python 3.11 tro len.
  pause
  exit /b 1
)
echo Dang kiem tra Flow Agent (8001) va FlowKit (8100)...
py -3 -c "import urllib.request; [(lambda u: print(u, 'dang phan hoi' if urllib.request.urlopen(u, timeout=1).status < 500 else 'loi'))(u) for u in ['http://127.0.0.1:8001/health','http://127.0.0.1:8100/api/providers/status']]" 2>nul
if errorlevel 1 echo Khong phat hien mot hoac ca hai provider. Giao dien van mo duoc; tao video se bi vo hieu hoa.
echo Khoi dong connector cuc bo. Khong mo cong ra Internet.
py -3 connector.py
if errorlevel 1 (
  echo Connector dung dot ngot. Hay kiem tra loi o tren.
  pause
)
endlocal
