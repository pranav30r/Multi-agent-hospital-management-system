# Multi-Agent Hospital Management System

Production-grade multi-agent AI system for hospital resource optimization, clinical workflow automation, and patient care coordination.

## Architecture

- **Backend:** Python 3.11+ / FastAPI / SQLAlchemy 2.0 (async)
- **Database:** PostgreSQL 15+ (SQLite fallback for dev)
- **Cache/Pub-Sub:** Redis 7.0+
- **AI Agents:** LangGraph + CrewAI (Person 2)
- **Frontend:** React Command Center (Person 3)
- **Infra:** Docker Compose

## Team Branches

| Branch | Owner | Scope |
|--------|-------|-------|
| `feature/backend-core` | Person 1 | DB Models, REST API, WebSocket, Seed Data |
| `feature/ai-agents` | Person 2 | Event Bus, 6 AI Agents, Prediction Engine |
| `feature/frontend-ui` | Person 3 | React Command Center Dashboard |

## Quick Start (Backend)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs at: `http://localhost:8000/docs`

## Backend Stats

- **28** SQLAlchemy models
- **44** REST API routes across 9 routers
- **40** ICD-10 coded diseases in registry
- **WebSocket** real-time event streaming at `/ws/events`
