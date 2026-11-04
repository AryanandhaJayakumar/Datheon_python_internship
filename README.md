# Datheon Python Internship Projects

This repository contains two Python backend projects developed as part of my **Datheon Python Backend Development Internship**. These projects helped me gain practical experience in building REST APIs, validating data, implementing authentication, and managing role-based access.

## 📌 Projects Overview

### Task 1: Pageora – BookStore REST API

**Description**

Pageora is a BookStore REST API built using FastAPI and Pydantic. It provides endpoints to manage book information, validate book details, search and filter the catalogue, and view statistics. The project also includes a simple web interface for interacting with the API.

**Key Features**
- Create, read, update, and delete books (CRUD operations).
- Validate book details using Pydantic.
- Validate ISBN-10 and ISBN-13 numbers.
- Prevent duplicate ISBN entries.
- Search and filter books by title, author, genre, year, price, and availability.
- Support pagination using `skip` and `limit`.
- View book catalogue statistics.
- Explore and test endpoints through Swagger UI.
- Use an asynchronous in-memory repository.

**Technologies Used**
- Python
- FastAPI
- Pydantic v2
- Uvicorn
- HTML, CSS, and JavaScript

**How to Run**

```bash
cd task1
pip install fastapi uvicorn pydantic
python main.py
```

Open the following URLs in your browser:

- Website: http://127.0.0.1:8000
- Swagger UI: http://127.0.0.1:8000/docs

---

### Task 2: AuthNexa – User Authentication & Role-Based Access Control

**Description**

AuthNexa is a user authentication and authorization application built using FastAPI. It uses JSON Web Tokens (JWT) for authentication, bcrypt for password hashing, and role-based access control (RBAC) to distinguish administrator permissions from regular user permissions. The project includes a web dashboard and an interactive API tester.

**Key Features**
- Register new user accounts and log in.
- Authenticate users using JWT access tokens.
- Hash passwords using bcrypt.
- Validate usernames and password requirements.
- Protect endpoints using OAuth2 Bearer authentication.
- Implement role-based access for administrators and regular users.
- View the logged-in user's profile and account statistics.
- Allow administrators to list users, change roles, and delete accounts.
- Test authenticated and unauthorized API requests.
- Explore endpoints through Swagger UI.

**Technologies Used**
- Python
- FastAPI
- Pydantic
- JWT (`python-jose`)
- Passlib and bcrypt
- OAuth2
- HTML, CSS, and JavaScript

**How to Run**

```bash
cd task2
pip install fastapi uvicorn python-multipart "python-jose[cryptography]" "passlib[bcrypt]" "bcrypt==4.0.1"
python main.py
```

Open the following URLs in your browser:

- Website: http://127.0.0.1:8000
- Swagger UI: http://127.0.0.1:8000/docs

**Demo Admin Account**

- Username: `admin`
- Password: `Admin@123`

Use this account only for local demonstration and testing.

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
├── .gitignore
└── README.md
```

*The structure above assumes the listed files are present in your repository. Adjust it if your actual filenames differ.*

## 🎯 Learning Outcomes

Through these projects, I gained practical experience in:

- Building REST APIs with FastAPI.
- Using Pydantic for request validation and data modelling.
- Implementing asynchronous API operations.
- Working with CRUD operations and HTTP status codes.
- Implementing JWT authentication and password hashing.
- Applying role-based authorization.
- Testing APIs using Swagger UI.
- Connecting frontend interfaces with backend endpoints.

## ⚠️ Notes

- Both projects use in-memory storage, so application data is not permanently saved and may reset when the server restarts.
- These projects are intended for learning and demonstration. Production applications require additional security measures, persistent database storage, and appropriate secret-key management.

## 🙏 Acknowledgement

Thanks to **Datheon** for providing the opportunity to practise Python backend development through hands-on internship tasks.
