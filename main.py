import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from database import init_db
from routers import courses, topics, facts, questions, flags

app = FastAPI(title="QuizBase")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(courses.router)
app.include_router(topics.router)
app.include_router(facts.router)
app.include_router(questions.router)
app.include_router(flags.router)


@app.on_event("startup")
async def startup():
    await init_db()


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
