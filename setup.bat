@echo off
echo ====================================
echo FO Intelligence — Setup
echo ====================================

echo.
echo [1/4] Creating virtual environment...
python -m venv venv
call venv\Scripts\activate

echo.
echo [2/4] Installing dependencies...
pip install -r requirements.txt

echo.
echo [3/4] Creating data directories...
mkdir data\raw 2>nul
mkdir data\processed 2>nul

echo.
echo [4/4] Checking .env file...
if not exist .env (
    echo ERROR: .env file not found! Copy .env.example to .env and add your API keys.
    exit /b 1
)

echo.
echo ====================================
echo Setup complete!
echo.
echo Next steps:
echo   1. python run_pipeline.py    (generate dataset + index)
echo   2. python test_rag.py        (test RAG queries)
echo   3. uvicorn src.api.main:app --reload --port 8000
echo ====================================
