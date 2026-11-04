@echo off
chcp 65001 >nul
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js 24 LTS를 먼저 설치해 주세요.
  pause
  exit /b 1
)
if not exist node_modules (
  call npm ci
  if errorlevel 1 (
    echo 설치가 완료되지 않았습니다. 인터넷 연결을 확인해 주세요.
    pause
    exit /b 1
  )
)
echo 브라우저에서 http://127.0.0.1:5173 을 열어 주세요.
call npm run dev
pause
