# Ansible Playbook Debugging AI Agent

This repository contains a starter AI agent to help debug Ansible playbook execution, recommend fixes, and integrate with AWX, GitHub, Microsoft Teams, and PostgreSQL. The implementation is a scaffolded FastAPI service with clients and docker-compose for local testing.

Features:
- Connect to AWX (read-only) to fetch job logs
- Connect to GitHub to read roles and manage issues
- Send/receive messages to Microsoft Teams (via incoming webhook + webhook endpoint)
- Basic Ansible log analyzer that suggests fixes
- LangChain/ Ollama model connector placeholder for advanced recommendations
- PostgreSQL integration for logging requests
- Runnable locally and via Docker Compose

See `docs/` for architecture, design, and deployment instructions.

Getting started
 - Copy `.env.example` to `.env` and fill required values.
 - Local dev with venv: see `docs/local_testing.md`.
 - To run with Docker: `docker compose up --build`.

Docs
 - Architecture: `docs/architecture.md`
 - Local testing: `docs/local_testing.md`

# ai-agent-playbook-debugging
AI Agent for ansible playbook debugging and recommentaions
