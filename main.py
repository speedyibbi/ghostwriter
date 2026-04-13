import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import books, chapters, workflow

app = FastAPI(title="Ghostwriter", version="0.1.0")

app.include_router(books.router,    prefix="/api/books",    tags=["books"])
app.include_router(chapters.router, prefix="/api/chapters", tags=["chapters"])
app.include_router(workflow.router, prefix="/api/workflow", tags=["workflow"])

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", include_in_schema=False)
async def index():
    return FileResponse("static/index.html")

@app.get("/book/{book_id}", include_in_schema=False)
async def book_page(book_id: str):
    return FileResponse("static/book.html")

@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
