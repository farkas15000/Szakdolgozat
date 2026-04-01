from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI()


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
