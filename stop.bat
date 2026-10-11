@echo off
echo Stopping PostgreSQL Server...
"C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe" stop -D "%~dp0pgdata"
echo PostgreSQL stopped.
pause
