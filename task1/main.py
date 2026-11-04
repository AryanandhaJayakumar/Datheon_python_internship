"""
BookStore REST API
------------------
Asynchronous CRUD API built with FastAPI + Pydantic v2.

Frontend + backend in ONE file.

Run:
    pip install fastapi uvicorn pydantic
    python main.py

Website:     http://127.0.0.1:8000
Swagger UI:  http://127.0.0.1:8000/docs
"""

import asyncio
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

SEED_ON_STARTUP = True  # set to False to start with an empty library


@asynccontextmanager
async def lifespan(_: FastAPI):
    if SEED_ON_STARTUP:
        await seed_books()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="BookStore API",
    description="A simple asynchronous CRUD API for managing books.",
    version="1.0.0",
    swagger_ui_parameters={
        "syntaxHighlight.theme": "monokai",
        "displayRequestDuration": True,
        "defaultModelsExpandDepth": -1,
        "docExpansion": "list",
    },
)


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class Genre(str, Enum):
    fiction = "fiction"
    non_fiction = "non-fiction"
    science = "science"
    technology = "technology"
    history = "history"
    fantasy = "fantasy"
    biography = "biography"
    other = "other"


def _isbn10_ok(d: str) -> bool:
    total = sum((10 if c == "X" else int(c)) * (10 - i) for i, c in enumerate(d))
    return total % 11 == 0


def _isbn13_ok(d: str) -> bool:
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(d))
    return total % 10 == 0


SAMPLE_BOOKS = [
    {"title": "Clean Code", "author": "Robert C. Martin", "isbn": "978-0132350884", "genre": "technology", "published_year": 2008, "price": 34.99, "in_stock": True},
    {"title": "Sapiens", "author": "Yuval Noah Harari", "isbn": "978-0062316097", "genre": "history", "published_year": 2015, "price": 18.5, "in_stock": True},
    {"title": "The Hobbit", "author": "J.R.R. Tolkien", "isbn": "978-0547928227", "genre": "fantasy", "published_year": 1937, "price": 12.99, "in_stock": False},
    {"title": "A Brief History of Time", "author": "Stephen Hawking", "isbn": "978-0553380163", "genre": "science", "published_year": 1988, "price": 16.0, "in_stock": True},
    {"title": "Dune", "author": "Frank Herbert", "isbn": "978-0441013593", "genre": "fiction", "published_year": 1965, "price": 9.99, "in_stock": True},
    {"title": "1984", "author": "George Orwell", "isbn": "978-0451524935", "genre": "fiction", "published_year": 1949, "price": 8.99, "in_stock": True},
    {"title": "Atomic Habits", "author": "James Clear", "isbn": "978-0735211292", "genre": "non-fiction", "published_year": 2018, "price": 16.99, "in_stock": True},
    {"title": "The Pragmatic Programmer", "author": "Andrew Hunt", "isbn": "978-0135957059", "genre": "technology", "published_year": 2019, "price": 39.99, "in_stock": True},
    {"title": "Educated", "author": "Tara Westover", "isbn": "978-0399590504", "genre": "biography", "published_year": 2018, "price": 17.0, "in_stock": True},
    {"title": "Harry Potter and the Sorcerer's Stone", "author": "J.K. Rowling", "isbn": "978-0590353427", "genre": "fantasy", "published_year": 1998, "price": 10.99, "in_stock": True},
    {"title": "The Great Gatsby", "author": "F. Scott Fitzgerald", "isbn": "978-0743273565", "genre": "fiction", "published_year": 1925, "price": 10.5, "in_stock": True},
    {"title": "To Kill a Mockingbird", "author": "Harper Lee", "isbn": "978-0061120084", "genre": "fiction", "published_year": 1960, "price": 11.99, "in_stock": False},
    {"title": "Pride and Prejudice", "author": "Jane Austen", "isbn": "978-0141439518", "genre": "fiction", "published_year": 1813, "price": 7.99, "in_stock": True},
    {"title": "The Alchemist", "author": "Paulo Coelho", "isbn": "978-0062315007", "genre": "fiction", "published_year": 1988, "price": 14.99, "in_stock": True},
    {"title": "Cosmos", "author": "Carl Sagan", "isbn": "978-0345539434", "genre": "science", "published_year": 1980, "price": 15.99, "in_stock": True},
    {"title": "The Selfish Gene", "author": "Richard Dawkins", "isbn": "978-0198788607", "genre": "science", "published_year": 1976, "price": 14.5, "in_stock": False},
    {"title": "Steve Jobs", "author": "Walter Isaacson", "isbn": "978-1451648539", "genre": "biography", "published_year": 2011, "price": 19.99, "in_stock": True},
    {"title": "Becoming", "author": "Michelle Obama", "isbn": "978-1524763138", "genre": "biography", "published_year": 2018, "price": 18.99, "in_stock": True},
    {"title": "Guns, Germs, and Steel", "author": "Jared Diamond", "isbn": "978-0393317558", "genre": "history", "published_year": 1997, "price": 17.95, "in_stock": True},
    {"title": "The Name of the Wind", "author": "Patrick Rothfuss", "isbn": "978-0756404741", "genre": "fantasy", "published_year": 2007, "price": 9.99, "in_stock": True},
    {"title": "A Game of Thrones", "author": "George R.R. Martin", "isbn": "978-0553593716", "genre": "fantasy", "published_year": 1996, "price": 12.99, "in_stock": True},
    {"title": "Introduction to Algorithms", "author": "Thomas H. Cormen", "isbn": "978-0262033848", "genre": "technology", "published_year": 2009, "price": 89.0, "in_stock": False},
    {"title": "Python Crash Course", "author": "Eric Matthes", "isbn": "978-1593279288", "genre": "technology", "published_year": 2019, "price": 31.99, "in_stock": True},
    {"title": "Fluent Python", "author": "Luciano Ramalho", "isbn": "978-1491946008", "genre": "technology", "published_year": 2015, "price": 54.99, "in_stock": True},
    {"title": "Thinking, Fast and Slow", "author": "Daniel Kahneman", "isbn": "978-0374533557", "genre": "non-fiction", "published_year": 2011, "price": 16.0, "in_stock": True},
    {"title": "The Diary of a Young Girl", "author": "Anne Frank", "isbn": "978-0553296983", "genre": "biography", "published_year": 1947, "price": 9.5, "in_stock": True},
    {"title": "Astrophysics for People in a Hurry", "author": "Neil deGrasse Tyson", "isbn": "978-0393609394", "genre": "science", "published_year": 2017, "price": 13.95, "in_stock": True},
    {"title": "The Immortal Life of Henrietta Lacks", "author": "Rebecca Skloot", "isbn": "978-1400052189", "genre": "non-fiction", "published_year": 2010, "price": 16.99, "in_stock": True},
]


class BookBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, examples=["Clean Code"])
    author: str = Field(..., min_length=1, max_length=100, examples=["Robert C. Martin"])
    isbn: str = Field(..., examples=["978-0132350884"], description="ISBN-10 or ISBN-13")
    genre: Genre = Genre.other
    published_year: int = Field(..., ge=1000, le=datetime.now().year, examples=[2008])
    price: float = Field(..., gt=0, le=10_000, examples=[34.99])
    in_stock: bool = True

    @field_validator("isbn")
    @classmethod
    def validate_isbn(cls, v: str) -> str:
        digits = re.sub(r"[-\s]", "", v).upper()
        if re.fullmatch(r"\d{9}[\dX]", digits):
            ok = _isbn10_ok(digits)
        elif re.fullmatch(r"\d{13}", digits):
            ok = _isbn13_ok(digits)
        else:
            ok = False
        if not ok:
            raise ValueError("Invalid ISBN: check the digits (ISBN-10 or ISBN-13 checksum failed)")
        return digits

    @field_validator("title", "author")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class BookCreate(BookBase):
    """Payload for creating a book."""


class BookUpdate(BookBase):
    """Payload for replacing a book (PUT)."""


class Book(BookBase):
    """Book as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------
# In-memory async "database"
# --------------------------------------------------------------------------
class BookRepository:
    def __init__(self) -> None:
        self._books: dict[int, Book] = {}
        self._next_id = 1
        self._lock = asyncio.Lock()

    async def list(self) -> list[Book]:
        async with self._lock:
            return list(self._books.values())

    async def get(self, book_id: int) -> Optional[Book]:
        async with self._lock:
            return self._books.get(book_id)

    async def isbn_exists(self, isbn: str, exclude_id: Optional[int] = None) -> bool:
        async with self._lock:
            return any(
                b.isbn == isbn and b.id != exclude_id for b in self._books.values()
            )

    async def create(self, data: BookCreate) -> Book:
        async with self._lock:
            now = datetime.now(timezone.utc)
            book = Book(id=self._next_id, created_at=now, updated_at=now, **data.model_dump())
            self._books[book.id] = book
            self._next_id += 1
            return book

    async def update(self, book_id: int, data: BookUpdate) -> Optional[Book]:
        async with self._lock:
            existing = self._books.get(book_id)
            if existing is None:
                return None
            updated = existing.model_copy(
                update={**data.model_dump(), "updated_at": datetime.now(timezone.utc)}
            )
            self._books[book_id] = updated
            return updated

    async def delete(self, book_id: int) -> bool:
        async with self._lock:
            return self._books.pop(book_id, None) is not None


repo = BookRepository()


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------
@app.post(
    "/books",
    response_model=Book,
    status_code=status.HTTP_201_CREATED,
    tags=["Books"],
    summary="Create a new book",
)
async def create_book(book: BookCreate):
    if await repo.isbn_exists(book.isbn):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A book with ISBN {book.isbn} already exists.",
        )
    return await repo.create(book)


@app.get(
    "/books",
    response_model=list[Book],
    tags=["Books"],
    summary="List books with optional filtering",
)
async def list_books(
    author: Optional[str] = Query(None, description="Filter by author (partial, case-insensitive)"),
    title: Optional[str] = Query(None, description="Filter by title (partial, case-insensitive)"),
    genre: Optional[Genre] = Query(None, description="Filter by genre"),
    min_year: Optional[int] = Query(None, ge=1000, description="Published in or after this year"),
    max_year: Optional[int] = Query(None, ge=1000, description="Published in or before this year"),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    in_stock: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(10, ge=1, le=100, description="Max records to return"),
):
    if min_year and max_year and min_year > max_year:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="min_year cannot be greater than max_year.",
        )
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="min_price cannot be greater than max_price.",
        )

    books = await repo.list()

    if author:
        books = [b for b in books if author.lower() in b.author.lower()]
    if title:
        books = [b for b in books if title.lower() in b.title.lower()]
    if genre:
        books = [b for b in books if b.genre == genre]
    if min_year is not None:
        books = [b for b in books if b.published_year >= min_year]
    if max_year is not None:
        books = [b for b in books if b.published_year <= max_year]
    if min_price is not None:
        books = [b for b in books if b.price >= min_price]
    if max_price is not None:
        books = [b for b in books if b.price <= max_price]
    if in_stock is not None:
        books = [b for b in books if b.in_stock == in_stock]

    return books[skip : skip + limit]


@app.get("/books/stats", tags=["Books"], summary="Catalogue totals")
async def book_stats():
    books = await repo.list()
    return {
        "total": len(books),
        "in_stock": sum(1 for b in books if b.in_stock),
        "value": round(sum(b.price for b in books), 2),
    }


@app.post("/books/seed", tags=["Books"], summary="Load sample books (skips ISBNs that already exist)")
async def seed_books():
    added = skipped = 0
    for raw in SAMPLE_BOOKS:
        data = BookCreate(**raw)
        if await repo.isbn_exists(data.isbn):
            skipped += 1
            continue
        await repo.create(data)
        added += 1
    return {"added": added, "skipped": skipped}


@app.get(
    "/books/{book_id}",
    response_model=Book,
    tags=["Books"],
    summary="Get a book by ID",
)
async def get_book(book_id: int):
    book = await repo.get(book_id)
    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with id {book_id} not found.",
        )
    return book


@app.put(
    "/books/{book_id}",
    response_model=Book,
    tags=["Books"],
    summary="Replace an existing book",
)
async def update_book(book_id: int, book: BookUpdate):
    if await repo.get(book_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with id {book_id} not found.",
        )
    if await repo.isbn_exists(book.isbn, exclude_id=book_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Another book with ISBN {book.isbn} already exists.",
        )
    return await repo.update(book_id, book)


@app.delete(
    "/books/{book_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Books"],
    summary="Delete a book",
)
async def delete_book(book_id: int):
    deleted = await repo.delete(book_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Book with id {book_id} not found.",
        )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home():
    return HTML_PAGE


# --------------------------------------------------------------------------
# Frontend (served at "/")
# --------------------------------------------------------------------------
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pageora - BookStore</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#faf6ef;--card:#fff;--ink:#1f1b2e;--muted:#6b667a;--line:#ece5d8;--accent:#5b3df5;--ok:#16a34a;--bad:#dc2626;--shadow:0 10px 30px -14px rgba(40,25,90,.3)}
@media(prefers-color-scheme:dark){:root{--bg:#14121f;--card:#1e1b2e;--ink:#f3f0ff;--muted:#9a95b0;--line:#2e2a44;--shadow:0 10px 30px -14px rgba(0,0,0,.7)}}
*{box-sizing:border-box;margin:0}
html{scroll-behavior:smooth}
body{font-family:Inter,system-ui,sans-serif;background:var(--bg);color:var(--ink);min-height:100vh}
h1,h2,h3{font-family:Fraunces,Georgia,serif}
.wrap{max-width:1180px;margin:0 auto;position:relative;z-index:1}
/* hero */
.hero{background:linear-gradient(135deg,#2a14b8,#6d3df5 55%,#ff6b8b);color:#fff;padding:28px 24px 110px;position:relative;overflow:hidden}
.hero::before{content:"";position:absolute;width:420px;height:420px;border-radius:50%;background:rgba(255,255,255,.08);right:-120px;top:-160px}
nav{display:flex;justify-content:space-between;align-items:center;margin-bottom:56px}
.logo{font-family:Fraunces,serif;font-weight:800;font-size:1.5rem;letter-spacing:-.02em}
.logo span{opacity:.7}
.links a{color:#fff;text-decoration:none;font-size:.88rem;font-weight:500;padding:8px 16px;border:1px solid rgba(255,255,255,.4);border-radius:99px;margin-left:8px;transition:.2s}
.links a:hover{background:#fff;color:#2a14b8}
.heroGrid{display:grid;grid-template-columns:1.2fr .8fr;gap:30px;align-items:center}
.eyebrow{display:inline-block;font-size:.75rem;font-weight:600;text-transform:uppercase;letter-spacing:.12em;background:rgba(255,255,255,.16);padding:6px 14px;border-radius:99px;margin-bottom:18px}
.hero h1{font-size:clamp(2.3rem,5vw,3.8rem);line-height:1.04;font-weight:800;letter-spacing:-.03em}
.hero p.lead{margin:18px 0 26px;max-width:500px;opacity:.92;line-height:1.65}
.cta{display:flex;flex-wrap:wrap;gap:12px}
.btn{font:inherit;font-weight:600;border:0;border-radius:12px;padding:12px 22px;cursor:pointer;transition:.2s;color:#fff;background:linear-gradient(135deg,var(--accent),#8b5cf6);text-decoration:none;display:inline-flex;align-items:center;gap:8px}
.btn:hover{transform:translateY(-2px);box-shadow:0 10px 22px -8px rgba(91,61,245,.7)}
.btn:disabled{opacity:.6;cursor:wait;transform:none;box-shadow:none}
.btn.light{background:#fff;color:#2a14b8}
.btn.line{background:transparent;color:#fff;border:1.5px solid rgba(255,255,255,.55)}
.btn.line:hover{background:rgba(255,255,255,.14);box-shadow:none}
.btn.ghost{background:transparent;color:var(--ink);border:1.5px solid var(--line)}
.btn.ghost:hover{border-color:var(--accent);color:var(--accent);box-shadow:none}
.btn.danger{background:var(--bad)}
.stats{display:flex;gap:30px;margin-top:34px}
.stats b{font-family:Fraunces,serif;font-size:1.9rem;display:block}
.stats small{opacity:.8;font-size:.76rem;text-transform:uppercase;letter-spacing:.08em}
.art{position:relative;height:280px}
.bk{position:absolute;width:150px;height:210px;border-radius:6px 14px 14px 6px;box-shadow:-6px 12px 28px rgba(0,0,0,.35);display:flex;align-items:flex-end;padding:14px;font-family:Fraunces,serif;font-weight:800;font-size:1.1rem;border-left:8px solid rgba(0,0,0,.2);animation:float 6s ease-in-out infinite}
.b1{background:linear-gradient(145deg,#ffb86b,#ff6b8b);left:6%;top:40px;transform:rotate(-9deg)}
.b2{background:linear-gradient(145deg,#34d399,#0ea5e9);left:34%;top:6px;transform:rotate(3deg);animation-delay:-2s}
.b3{background:linear-gradient(145deg,#a78bfa,#6366f1);left:60%;top:50px;transform:rotate(11deg);animation-delay:-4s}
@keyframes float{50%{translate:0 -10px}}
/* toolbar */
main{margin-top:-62px;padding:0 24px 70px}
.toolbar{background:var(--card);border:1px solid var(--line);border-radius:20px;box-shadow:var(--shadow);padding:16px;display:grid;grid-template-columns:1.2fr 1.2fr repeat(3,1fr) auto;gap:12px;scroll-margin-top:20px}
input,select{font:inherit;color:var(--ink);background:var(--bg);border:1.5px solid var(--line);border-radius:12px;padding:11px 14px;width:100%;outline:none;transition:.2s}
input:focus,select:focus{border-color:var(--accent);box-shadow:0 0 0 4px rgba(91,61,245,.15)}
input.bad,select.bad{border-color:var(--bad);box-shadow:0 0 0 4px rgba(220,38,38,.12)}
.bar{display:flex;justify-content:space-between;align-items:center;gap:12px;margin:34px 0 18px;scroll-margin-top:20px}
.bar h2{font-size:1.5rem}
.bar small{color:var(--muted);font-family:Inter;font-size:.9rem;margin-left:8px}
/* cards */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:22px}
.card{background:var(--card);border-radius:20px;overflow:hidden;border:1px solid var(--line);box-shadow:var(--shadow);transition:.25s;display:flex;flex-direction:column;animation:rise .45s both}
.card:hover{transform:translateY(-7px);box-shadow:0 22px 40px -16px rgba(60,30,140,.4)}
@keyframes rise{from{opacity:0;transform:translateY(14px)}}
.cover{height:178px;position:relative;display:flex;align-items:flex-end;padding:16px;color:#fff;overflow:hidden}
.cover::before{content:"";position:absolute;left:0;top:0;bottom:0;width:10px;background:rgba(0,0,0,.18)}
.cover .ini{position:absolute;right:12px;top:-22px;font-family:Fraunces,serif;font-weight:800;font-size:8rem;opacity:.2;line-height:1;transition:.4s}
.card:hover .ini{transform:scale(1.12) rotate(-4deg)}
.tag{font-size:.7rem;font-weight:600;text-transform:uppercase;letter-spacing:.08em;background:rgba(255,255,255,.22);backdrop-filter:blur(6px);padding:5px 11px;border-radius:99px;position:relative}
.cbody{padding:18px;display:flex;flex-direction:column;gap:5px;flex:1}
.cbody h3{font-size:1.15rem;line-height:1.25}
.by{color:var(--muted);font-size:.9rem}
.isbn{font-size:.72rem;color:var(--muted)}
.meta{display:flex;justify-content:space-between;align-items:center;margin-top:auto;padding-top:14px}
.price{font-family:Fraunces,serif;font-weight:800;font-size:1.4rem;color:var(--accent)}
.stock{font-size:.75rem;font-weight:600;padding:4px 10px;border-radius:99px}
.in{background:rgba(22,163,74,.14);color:var(--ok)}.out{background:rgba(220,38,38,.14);color:var(--bad)}
.acts{display:flex;gap:8px;padding:0 18px 18px}
.acts button{flex:1;font:inherit;font-size:.85rem;font-weight:600;padding:9px;border-radius:10px;cursor:pointer;border:1.5px solid var(--line);background:transparent;color:var(--ink);transition:.2s}
.acts [data-edit]:hover{border-color:var(--accent);color:var(--accent)}
.acts [data-del]:hover{border-color:var(--bad);color:var(--bad)}
.sk{height:330px;border-radius:20px;background:linear-gradient(90deg,var(--card) 25%,var(--line) 50%,var(--card) 75%);background-size:200% 100%;animation:sh 1.2s infinite;border:1px solid var(--line)}
@keyframes sh{to{background-position:-200% 0}}
.empty{grid-column:1/-1;text-align:center;padding:60px 20px;background:var(--card);border:2px dashed var(--line);border-radius:20px}
.empty .big{font-size:3rem}
.empty p{color:var(--muted);margin:8px 0 22px}
.empty .row{display:flex;gap:10px;justify-content:center;flex-wrap:wrap}
/* dialogs */
dialog{border:0;border-radius:24px;padding:0;width:min(540px,92vw);background:var(--card);color:var(--ink);box-shadow:0 30px 80px -10px rgba(0,0,0,.5)}
dialog::backdrop{background:rgba(20,10,50,.55);backdrop-filter:blur(4px)}
form{padding:28px;display:grid;grid-template-columns:1fr 1fr;gap:14px}
form h2{grid-column:1/-1;font-size:1.5rem}
label{font-size:.78rem;font-weight:600;color:var(--muted);display:flex;flex-direction:column;gap:6px}
.full{grid-column:1/-1}
.chk{flex-direction:row;align-items:center;gap:10px;font-size:.9rem;color:var(--ink)}
.chk input{width:auto}
.fe{font-style:normal;font-weight:500;font-size:.76rem;color:var(--bad);min-height:0}
.err{grid-column:1/-1;color:var(--bad);font-size:.85rem;font-weight:500}
.foot{grid-column:1/-1;display:flex;justify-content:flex-end;gap:10px}
.confirm{padding:28px;text-align:center}
.confirm h3{font-size:1.3rem;margin-bottom:8px}
.confirm p{color:var(--muted);margin-bottom:22px;line-height:1.5}
.confirm .foot{justify-content:center}
#toasts{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);display:grid;gap:8px;z-index:20;width:max-content;max-width:92vw}
.toast{background:var(--ink);color:var(--bg);padding:12px 20px;border-radius:99px;font-weight:500;font-size:.9rem;box-shadow:var(--shadow);animation:rise .3s both;display:flex;gap:8px;align-items:center}
.toast.ok::before{content:"\2713";color:#34d399;font-weight:700}
.toast.err::before{content:"!";color:#fb7185;font-weight:800}
@media(max-width:980px){.toolbar{grid-template-columns:1fr 1fr}.toolbar .btn{grid-column:1/-1;justify-content:center}.heroGrid{grid-template-columns:1fr}.art{display:none}}
@media(max-width:560px){form{grid-template-columns:1fr}.links a:first-child{display:none}.stats{gap:20px}.toolbar{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
</head>
<body>
<header class="hero">
  <div class="wrap">
    <nav>
      <div class="logo">Pageora<span>.</span></div>
    </nav>
    <div class="heroGrid">
      <div>
        <span class="eyebrow">FastAPI &middot; Pydantic &middot; Async</span>
        <h1>Find your next favourite book.</h1>
        <p class="lead">Browse, search and manage a live catalogue.</p>
        <div class="cta">
          <a class="btn light" href="#library">Explore the library &darr;</a>
          <button class="btn line" id="heroAdd">+ Add a book</button>
        </div>
        <div class="stats">
          <div><b id="sCount">0</b><small>Books</small></div>
          <div><b id="sStock">0</b><small>In stock</small></div>
          <div><b id="sValue">$0</b><small>Catalogue value</small></div>
        </div>
      </div>
      <div class="art" aria-hidden="true"><div class="bk b1">Dune</div><div class="bk b2">Sapiens</div><div class="bk b3">1984</div></div>
    </div>
  </div>
</header>

<main>
  <div class="wrap">
    <section class="toolbar" id="filters" aria-label="Search and filters">
      <input id="fTitle" type="search" placeholder="Search title..." aria-label="Search title">
      <input id="fAuthor" type="search" placeholder="Search author..." aria-label="Search author">
      <select id="fGenre" aria-label="Genre"><option value="">All genres</option></select>
      <select id="fStock" aria-label="Availability"><option value="">Any availability</option><option value="true">In stock</option><option value="false">Out of stock</option></select>
      <select id="fSort" aria-label="Sort"><option value="new">Newest added</option><option value="title">Title A-Z</option><option value="pa">Price: low to high</option><option value="pd">Price: high to low</option><option value="year">Year published</option></select>
      <button class="btn" id="addBtn">+ Add book</button>
    </section>

    <div class="bar" id="library">
      <h2>Library<small id="resultInfo"></small></h2>
      <button class="btn ghost" id="seedBtn">Load sample books</button>
    </div>
    <section class="grid" id="grid" aria-live="polite"></section>
  </div>
</main>

<dialog id="dlg">
  <form id="form" novalidate>
    <h2 id="dlgTitle">Add a book</h2>
    <label class="full">Title<input name="title" maxlength="200" required><em class="fe" data-f="title"></em></label>
    <label class="full">Author<input name="author" maxlength="100" required><em class="fe" data-f="author"></em></label>
    <label>ISBN<input name="isbn" placeholder="978-0132350884" required><em class="fe" data-f="isbn"></em></label>
    <label>Genre<select name="genre" id="genreSel"></select><em class="fe" data-f="genre"></em></label>
    <label>Published year<input name="published_year" type="number" min="1000" required><em class="fe" data-f="published_year"></em></label>
    <label>Price ($)<input name="price" type="number" step="0.01" min="0.01" required><em class="fe" data-f="price"></em></label>
    <label class="chk full"><input name="in_stock" type="checkbox" checked> Available in stock</label>
    <div class="err" id="err" role="alert"></div>
    <div class="foot">
      <button type="button" class="btn ghost" id="cancel">Cancel</button>
      <button type="submit" class="btn" id="save">Save book</button>
    </div>
  </form>
</dialog>

<dialog id="cdlg">
  <div class="confirm">
    <h3>Delete this book?</h3>
    <p id="cText"></p>
    <div class="foot"><button class="btn ghost" id="cNo">Keep it</button><button class="btn danger" id="cYes">Delete</button></div>
  </div>
</dialog>
<div id="toasts"></div>

<script>
const GENRES=["fiction","non-fiction","science","technology","history","fantasy","biography","other"];
const PAL={fiction:["#6d28d9","#ec4899"],"non-fiction":["#0369a1","#22d3ee"],science:["#0f766e","#34d399"],technology:["#1d4ed8","#7c3aed"],history:["#b45309","#f59e0b"],fantasy:["#9d174d","#f97316"],biography:["#be123c","#fb7185"],other:["#475569","#94a3b8"]};
const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let books=[],editingId=null,deleteId=null,timer,reqSeq=0;

function toast(msg,type="ok"){
  const t=document.createElement("div");t.className="toast "+type;t.textContent=msg;
  $("#toasts").appendChild(t);setTimeout(()=>t.remove(),3200);
}

/* one place for every API call, so network and server errors are handled consistently */
async function http(path,opt){
  try{
    const r=await fetch(path,opt);let data=null;
    if(r.status!==204){try{data=await r.json()}catch(e){}}
    return {ok:r.ok,status:r.status,data};
  }catch(e){return {ok:false,status:0,data:null}}
}
function errMsg(res){
  if(res.status===0)return "Cannot reach the server. Is it still running?";
  if(res.status>=500)return "Server error. Please try again in a moment.";
  const d=res.data&&res.data.detail;
  return Array.isArray(d)?d.map(x=>x.msg.replace("Value error, ","")).join(", "):(d||"Request failed.");
}
const json=(m,b)=>({method:m,headers:{"Content-Type":"application/json"},body:JSON.stringify(b)});

GENRES.forEach(g=>{
  const o=`<option value="${g}">${g}</option>`;
  $("#fGenre").insertAdjacentHTML("beforeend",o);$("#genreSel").insertAdjacentHTML("beforeend",o);
});
document.querySelector('[name="published_year"]').max=new Date().getFullYear();

/* ---------- loading and rendering ---------- */
async function load(){
  const seq=++reqSeq;
  $("#grid").innerHTML='<div class="sk"></div>'.repeat(4);
  const p=new URLSearchParams({limit:100});
  if($("#fTitle").value.trim())p.set("title",$("#fTitle").value.trim());
  if($("#fAuthor").value.trim())p.set("author",$("#fAuthor").value.trim());
  if($("#fGenre").value)p.set("genre",$("#fGenre").value);
  if($("#fStock").value)p.set("in_stock",$("#fStock").value);
  const [r]=await Promise.all([http("/books?"+p),loadStats()]);
  if(seq!==reqSeq)return;
  if(!r.ok){
    $("#grid").innerHTML=`<div class="empty"><div class="big">&#9888;&#65039;</div><h3>Could not load books</h3><p>${esc(errMsg(r))}</p><div class="row"><button class="btn" onclick="load()">Try again</button></div></div>`;
    return;
  }
  books=r.data;render();
}
async function loadStats(){
  const r=await http("/books/stats");if(!r.ok)return;
  $("#sCount").textContent=r.data.total;$("#sStock").textContent=r.data.in_stock;
  $("#sValue").textContent="$"+Math.round(r.data.value).toLocaleString();
}
function sorted(list){
  const s=$("#fSort").value,a=[...list];
  if(s==="title")a.sort((x,y)=>x.title.localeCompare(y.title));
  else if(s==="pa")a.sort((x,y)=>x.price-y.price);
  else if(s==="pd")a.sort((x,y)=>y.price-x.price);
  else if(s==="year")a.sort((x,y)=>y.published_year-x.published_year);
  else a.sort((x,y)=>y.id-x.id);
  return a;
}
function render(){
  $("#resultInfo").textContent=books.length?`${books.length} ${books.length===1?"book":"books"}`:"";
  if(!books.length){
    const filtered=$("#fTitle").value||$("#fAuthor").value||$("#fGenre").value||$("#fStock").value;
    $("#grid").innerHTML=`<div class="empty"><div class="big">${filtered?"&#128269;":"&#128218;"}</div>
      <h3>${filtered?"No books match your filters":"Your library is empty"}</h3>
      <p>${filtered?"Try a different search or clear the filters.":"Add your first book or load a few samples to get started."}</p>
      <div class="row">${filtered?'<button class="btn" id="clearF">Clear filters</button>':'<button class="btn" data-open>+ Add book</button><button class="btn ghost" data-seed>Load samples</button>'}</div></div>`;
    return;
  }
  $("#grid").innerHTML=sorted(books).map((b,i)=>{
    const [c1,c2]=PAL[b.genre]||PAL.other;
    return `<article class="card" style="animation-delay:${Math.min(i,12)*45}ms">
      <div class="cover" style="background:linear-gradient(145deg,${c1},${c2})">
        <div class="ini">${esc(b.title[0].toUpperCase())}</div><span class="tag">${esc(b.genre)}</span></div>
      <div class="cbody"><h3>${esc(b.title)}</h3>
        <div class="by">by ${esc(b.author)} &middot; ${b.published_year}</div>
        <div class="isbn">ISBN ${esc(b.isbn)}</div>
        <div class="meta"><span class="price">$${b.price.toFixed(2)}</span>
        <span class="stock ${b.in_stock?"in":"out"}">${b.in_stock?"In stock":"Out of stock"}</span></div></div>
      <div class="acts"><button data-edit="${b.id}">Edit</button><button data-del="${b.id}">Delete</button></div></article>`;
  }).join("");
}

/* ---------- add / edit ---------- */
function setErrors(map,general){
  document.querySelectorAll(".fe").forEach(e=>e.textContent=map[e.dataset.f]||"");
  document.querySelectorAll("#form input,#form select").forEach(i=>i.classList.toggle("bad",!!map[i.name]));
  $("#err").textContent=general||"";
}
function openDlg(book){
  const f=$("#form");f.reset();setErrors({},"");
  editingId=book?book.id:null;
  $("#dlgTitle").textContent=book?"Edit book":"Add a book";
  $("#save").textContent=book?"Save changes":"Save book";
  if(book){
    for(const k of ["title","author","isbn","genre","published_year","price"])f.elements[k].value=book[k];
    f.elements.in_stock.checked=book.in_stock;
  }
  $("#dlg").showModal();f.elements.title.focus();
}
$("#form").addEventListener("submit",async e=>{
  e.preventDefault();
  const f=e.target.elements,errs={};
  if(!f.title.value.trim())errs.title="Title is required";
  if(!f.author.value.trim())errs.author="Author is required";
  if(!f.isbn.value.trim())errs.isbn="ISBN is required";
  if(!f.published_year.value)errs.published_year="Enter the year";
  if(!(+f.price.value>0))errs.price="Price must be above 0";
  if(Object.keys(errs).length){setErrors(errs,"");return}
  const body={title:f.title.value,author:f.author.value,isbn:f.isbn.value,genre:f.genre.value,
    published_year:+f.published_year.value,price:+f.price.value,in_stock:f.in_stock.checked};
  const btn=$("#save"),label=btn.textContent;btn.disabled=true;btn.textContent="Saving...";
  const r=await http(editingId?`/books/${editingId}`:"/books",json(editingId?"PUT":"POST",body));
  btn.disabled=false;btn.textContent=label;
  if(r.ok){$("#dlg").close();toast(editingId?"Book updated":"Book added");load();return}
  const map={};let general="";
  if(r.status===422&&Array.isArray(r.data&&r.data.detail)){
    r.data.detail.forEach(x=>{map[x.loc[x.loc.length-1]]=x.msg.replace("Value error, ","")});
  }else if(r.status===409){map.isbn=errMsg(r)}
  else general=errMsg(r);
  setErrors(map,general);
});

/* ---------- delete ---------- */
function askDelete(id){
  const b=books.find(x=>x.id===id);if(!b)return;
  deleteId=id;$("#cText").textContent=`"${b.title}" by ${b.author} will be removed permanently.`;$("#cdlg").showModal();
}
$("#cYes").onclick=async()=>{
  const btn=$("#cYes");btn.disabled=true;btn.textContent="Deleting...";
  const r=await http(`/books/${deleteId}`,{method:"DELETE"});
  btn.disabled=false;btn.textContent="Delete";$("#cdlg").close();
  if(r.ok||r.status===404){toast("Book deleted");load()}else toast(errMsg(r),"err");
};
$("#cNo").onclick=()=>$("#cdlg").close();

/* ---------- sample data (server skips ISBNs that already exist) ---------- */
async function seed(){
  const btn=$("#seedBtn");btn.disabled=true;
  const r=await http("/books/seed",{method:"POST"});
  btn.disabled=false;
  if(!r.ok){toast(errMsg(r),"err");return}
  toast(r.data.added?`Added ${r.data.added} sample ${r.data.added===1?"book":"books"}`+(r.data.skipped?` (${r.data.skipped} already there)`:""):"Sample books are already in your library");
  load();
}

/* ---------- events ---------- */
$("#grid").addEventListener("click",e=>{
  const t=e.target.closest("button");if(!t)return;
  if(t.dataset.edit)openDlg(books.find(b=>b.id===+t.dataset.edit));
  else if(t.dataset.del)askDelete(+t.dataset.del);
  else if(t.hasAttribute("data-open"))openDlg();
  else if(t.hasAttribute("data-seed"))seed();
  else if(t.id==="clearF"){["#fTitle","#fAuthor","#fGenre","#fStock"].forEach(s=>$(s).value="");load()}
});
$("#addBtn").onclick=$("#heroAdd").onclick=()=>openDlg();
$("#cancel").onclick=()=>$("#dlg").close();
$("#seedBtn").onclick=seed;
["#fTitle","#fAuthor"].forEach(s=>$(s).addEventListener("input",()=>{clearTimeout(timer);timer=setTimeout(load,300)}));
["#fGenre","#fStock"].forEach(s=>$(s).addEventListener("change",load));
$("#fSort").addEventListener("change",render);
load();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)