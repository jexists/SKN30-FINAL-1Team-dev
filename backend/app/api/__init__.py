from fastapi import APIRouter

from app.api import auth, customers, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(customers.router)
