# Datheon Python Internship Projects

This repository contains three Python backend projects developed as part of my **Datheon Python Backend Development Internship**. These projects helped me gain practical experience in REST API development, authentication, background processing, and Docker-based deployment.

## 📌 Projects Overview

### Task 1: Pageora – BookStore REST API

**Description**

Pageora is a BookStore REST API built using FastAPI and Pydantic. It supports book management, data validation, searching, filtering, and catalogue statistics through API endpoints and a web interface.

**Key Features**
- Create, read, update, and delete books (CRUD).
- Validate book details and ISBN-10/ISBN-13 numbers.
- Prevent duplicate ISBN entries.
- Search and filter books by title, author, genre, year, price, and availability.
- Support pagination.
- View catalogue statistics.
- Explore endpoints using Swagger UI.
- Use asynchronous in-memory storage.

**Technologies:** Python, FastAPI, Pydantic v2, Uvicorn, HTML, CSS, JavaScript.

**Run locally**

```bash
cd task1
pip install fastapi uvicorn pydantic
python main.py
```

- Website: http://127.0.0.1:8000
- Swagger UI: http://127.0.0.1:8000/docs

---

### Task 2: AuthNexa – User Authentication and RBAC

**Description**

AuthNexa is a user authentication and authorization application built with FastAPI. It uses JWT tokens, bcrypt password hashing, and role-based access control (RBAC) to manage access for regular users and administrators.

**Key Features**
- User registration and login.
- JWT-based authentication.
- Secure password hashing with bcrypt.
- OAuth2 Bearer token authentication.
- Protected API endpoints.
- Role-based permissions for administrators and users.
- Admin functions to list users, change roles, and delete accounts.
- User profile and account statistics.
- Interactive dashboard and API tester.
- Swagger UI integration.

**Technologies:** Python, FastAPI, Pydantic, JWT, OAuth2, Passlib, bcrypt, HTML, CSS, JavaScript.

**Run locally**

```bash
cd task2
pip install fastapi uvicorn python-multipart "python-jose[cryptography]" "passlib[bcrypt]" "bcrypt==4.0.1"
python main.py
```

- Website: http://127.0.0.1:8000
- Swagger UI: http://127.0.0.1:8000/docs

**Demo admin account**

- Username: `admin`
- Password: `Admin@123`

Use the demo account only for local testing.

---

### Task 3: Outbox – FastAPI Background-Task Microservice

**Description**

Outbox is a FastAPI microservice that queues email notifications and webhooks for background delivery. It includes retry handling, sender rate limiting, and Docker support for deployment.

**Key Features**
- Queue email and webhook notifications.
- Process notification deliveries in the background.
- Retry failed deliveries with exponential backoff.
- Limit the number of requests per client within a time window.
- Track job statuses, such as queued, sending, and delivered.
- Provide a health-check endpoint.
- Include interactive API documentation through Swagger UI.
- Support Docker and Docker Compose.
- Simulate email delivery when SMTP is not configured.

**Technologies:** Python, FastAPI, Uvicorn, Docker, Docker Compose, SMTP, REST APIs.

**Run with Docker**

```bash
docker build -t outbox .
docker run -d --name outbox -p 8000:8000 outbox
```

Alternatively, if a Docker Compose file is provided:

```bash
docker compose up --build
```

**Run without Docker**

```bash
python -m venv .venv
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Activate the virtual environment before installing dependencies if required by your operating system.

**Useful endpoints**

- Health check: `GET /health`
- Queue a notification: `POST /api/notifications`
- View jobs: `GET /api/jobs`
- Swagger UI: http://localhost:8000/docs

**Configuration**

| Variable | Default | Purpose |
|---|---|---|
| `RATE_LIMIT` | `5` | Maximum sends per client in a rate-limit window |
| `RATE_WINDOW` | `60` | Rate-limit window in seconds |
| `MAX_ATTEMPTS` | `3` | Maximum delivery attempts |
| `SMTP_HOST` | Unset | SMTP server for real email delivery |
| `SMTP_PORT` | Unset | SMTP server port |
| `SMTP_USER` | Unset | SMTP username |
| `SMTP_PASSWORD` | Unset | SMTP password |
| `SMTP_FROM` | Unset | Sender email address |
| `TRUST_PROXY` | `false` | Whether to trust `X-Forwarded-For` |
| `ALLOW_PRIVATE_WEBHOOKS` | `false` | Whether to allow private-network webhook targets |

**Important Notes**
- Job data and rate-limit counters are stored in memory.
- The service is designed to run with one worker under the current storage approach.
- For production use, persistent shared storage and a task queue such as Redis with Celery or ARQ may be appropriate.
- Configure SMTP credentials to enable real email delivery.

---

## 📁 Repository Structure

```text
Datheon_python_internship/
│
├── task1/
│   ├── main.py
│   └── main_updated.py
│
├── task2/
│   └── main.py
│
├── task3/
│   ├── app/
│   │   └── main.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── .gitignore
└── README.md
```

*Update the folder and file names in this example to match your actual repository.*

## 🎯 Learning Outcomes

Through these projects, I gained practical experience in:

- Developing REST APIs using FastAPI.
- Performing CRUD operations and validating request data.
- Implementing JWT authentication and role-based authorization.
- Hashing passwords and protecting API endpoints.
- Processing background notification tasks.
- Handling retries and rate limiting.
- Testing APIs with Swagger UI.
- Containerizing applications using Docker.

## ⚠️ General Notes

These projects are intended for learning and demonstration. Before production deployment, consider persistent database storage, secure secret management, proper access controls, and additional security testing.

## 🙏 Acknowledgement

Thanks to **Datheon** for providing the opportunity to practise Python backend development through hands-on internship projects.
