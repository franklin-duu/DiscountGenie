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

DB_HOST=db
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=password
DB_NAME=steam_sales
AI_SERVICE_URL=http://ai-service:8000

---

## Initial Setup Commands
### --- Frontend Setup ---
```bash
cd frontend
npm install
```

### --- Database & Docker Services Setup ---
```bash
# Ensure you are in the project root directory containing docker-compose.yml
docker-compose build
```

---

## Run Commands

### --- Run Backend ---
```bash
docker-compose up
```

### --- Run Frontend (In seperate terminal) ---
```bash
cd client
npm run dev
```

---

## Stopping The Application

### --- Stop Frontend---
```bash
Ctrl + C
```

### --- Stop Backend & Docker Services---
```bash
Ctrl + C
# OR run the following to tear down the containers completely:
docker-compose down
```

---

## Notes
- PostgreSQL, the Python AI microservice, and the Node.js backend run entirely inside Docker containers.
- The React frontend runs locally via Vite on your host machine.
- Only run npm install and initial setup steps once.
- Make sure Docker Desktop is running on your machine before executing docker-compose up.