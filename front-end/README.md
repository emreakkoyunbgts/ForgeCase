# Project Overview

This project consists of a modern frontend client communicating via Axios with multiple modular FastAPI microservices.

---

## Services & Ports

| Service           | Technology   | Port   | Description                            |
| :---------------- | :----------- | :----- | :------------------------------------- |
| **Frontend**      | Vite / React | `5173` | User interface (configured with Axios) |
| **Vault API**     | FastAPI      | `8000` | Secure storage & credentials service   |
| **Generator API** | FastAPI      | `8001` | Content / data generation engine       |
| **Librarian API** | FastAPI      | `8002` | Indexing & resource management         |
| **Reader API**    | FastAPI      | `8004` | Document parsing & ingestion service   |
| **Analyst API**   | FastAPI      | `8006` | Data processing & analytics engine     |

---

## Getting Started

### 1. Backend Microservices (FastAPI)

Run each service in its respective directory or virtual environment using `uvicorn`.

```bash
# Terminal 1 - Vault API
python -m vault.vault serve

# Terminal 2 - Generator API
uvicorn generator.GeneratorController:app --host 0.0.0.0 --port 8001 --reload

# Terminal 3 - Librarian API
uvicorn librarian.service:app --host 0.0.0.0 --port 8002 --reload

# Terminal 4 - Reader API
python -m reader.api serve

# Terminal 5 - Analyst API
uvicorn analyst.api:app --host 0.0.0.0 --port 8006 --reload
```
