.PHONY: backend frontend test run build

backend:
	cd backend && python3 -m pip install -r requirements.txt

frontend:
	cd frontend && npm install

test:
	cd backend && python3 -m pytest -q

build:
	cd frontend && npm install && npm run build

run: build
	cd backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8080
