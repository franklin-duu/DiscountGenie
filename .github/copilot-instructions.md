# Repository Instructions

## Project Structure

- `client/` is the React 18 frontend built with Vite. Keep browser UI changes here.
- `server/` is the Express backend. It calls the AI service and owns HTTP API behavior.
- `ai-service/` is the FastAPI Python service and owns Steam data access and prediction behavior.
- `sql/schema.sql` defines the PostgreSQL schema; `docker-compose.yml` runs the database, backend, and AI service.

## Commands

- Frontend development: `cd client && npm run dev`
- Frontend checks: `cd client && npm run lint` and `cd client && npm run build`
- Backend development: `cd server && npm run dev`; production-style start: `cd server && npm start`
- Python tests: `cd ai-service && python -m unittest discover -s tests`
- Run backend services and database: `docker-compose up` from the repository root.

## Working Conventions

- Keep changes within the service that owns the behavior; update callers when changing a cross-service API.
- Preserve existing HTTP paths, request/response fields, and database schema behavior unless the task explicitly requires a contract change.
- Add or update focused tests for behavior changes. Python tests use `unittest`; the client and server currently have no configured test scripts.
- Do not commit secrets or local environment files. Runtime configuration is supplied through environment variables and Docker Compose.
- Prefer small, focused changes and follow the language and formatting style already present in the touched files.