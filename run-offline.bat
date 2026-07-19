@echo off
where docker >nul 2>nul
if errorlevel 1 (
  echo Docker Desktop no esta instalado o no esta iniciado.
  exit /b 1
)

docker compose up --build
