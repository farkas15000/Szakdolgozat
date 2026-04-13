from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.backend.app.core.database import get_db
from src.backend.app.routers.auth_router import router as auth_router
from src.backend.app.routers.movies_router import router as movies_router
from src.backend.app.routers.ratings_router import router as ratings_router
from src.backend.app.routers.interactions_router import router as interactions_router

app = FastAPI()
app.include_router(auth_router, prefix="/api/v1")
app.include_router(movies_router, prefix="/api/v1")
app.include_router(ratings_router, prefix="/api/v1")
app.include_router(interactions_router, prefix="/api/v1")


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    return {"status": "ok"}


class Item(BaseModel):
    text: str = None
    is_done: bool = False

items = []

@app.get("/", response_class=HTMLResponse)
@app.get("/posts", response_class=HTMLResponse, include_in_schema=False)
def index():
    return f"<h1>Hello {1+1}</h1>"

@app.post("/items")
def create_item(item: Item):
    items.append(item)
    return items

@app.get("/items", response_model=list[Item])
def list_items(limit: int = 10):
    return items[:limit]

@app.get("/items/{item_id}", response_model=Item)
def get_item(item_id: int) -> Item:
    if item_id < len(items):
        return items[item_id]
    else:
        raise HTTPException(status_code=404, detail="Item not found")
