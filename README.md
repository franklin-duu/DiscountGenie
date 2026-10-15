# READ ME

## Table of Contents
- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
- [Setup Commands](#initial-setup-commands)
- [Run Commands](#run-commands)
- [Stopping the Application](#stopping-the-application)
- [Notes](#notes)

---

## Prerequisites
- Node.js
- Python 3.x
- PostgreSQL (running locally)

---

## Environment Variables
Create a `.env` file in the `backend` directory and add your MySQL credentials:

DB_HOST= 

DB_PORT=

DB_USER=

DB_PASSWORD=

DB_NAME=

---

## Initial Setup Commands
### --- Frontend Setup ---
```bash
cd frontend
npm install
```

### --- Backend Setup ---
```bash
cd backend
python -m venv venv

for mac: source venv/bin/activate

for windows: venv\Scripts\activate
pip install -r requirements.txt
```

### --- Database Setup ---
```bash
cd db
psql -U postgres
CREATE DATABASE steam_sales;
\c steam_sales;
\i schema.sql;

To check:
\c steam_sales;
\dt
SELECT * FROM games;
```

---

## Run Commands

### --- Run Backend ---
```bash
cd backend
for mac: source venv/bin/activate
for windows: venv\Scripts\activate
uvicorn main:app --reload
```

### --- Run Frontend ---
```bash
cd frontend
npm run dev
```

---

## Stopping The Application

### --- Stop Frontend---
```bash
Ctrl + C
```

### --- Stop Backend ---
```bash
Ctrl + C
deactivate
```

---

## Notes
- Only run setup steps once  
- Make sure PostgreSQL is running locally  
- Backend will fail if `.env` is not configured properly  