@echo off
REM Arranque de desarrollo: escucha en todas las interfaces para que
REM el telefono pueda conectarse por la IP local (ej. 192.168.x.x:8000).
cd /d "%~dp0"
uvicorn main:app --host 0.0.0.0 --port 8000 --reload