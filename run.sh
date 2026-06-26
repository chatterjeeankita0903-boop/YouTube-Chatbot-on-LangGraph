#!/usr/bin/env bash
set -e
[ -d venv ] || python3 -m venv venv
source venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || { cp .env.example .env; echo ">> Created .env — add your OPENAI_API_KEY, then re-run."; exit 1; }
echo ">> http://localhost:5000"
python app.py
