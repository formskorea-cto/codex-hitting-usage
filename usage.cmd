@echo off
chcp 65001 >nul
python "%~dp0codex_usage.py" --chart %*
