from fastapi import FastAPI
from app.api import events, transactions, reconciliation, seed
from app.db.database import engine, Base
import app.models.models 

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.include_router(seed.router)
app.include_router(events.router)
app.include_router(transactions.router)
app.include_router(reconciliation.router)


@app.get("/")
def root():
    return {"message": "Hey there I am up and running!"}
