from fastapi import APIRouter

from app.api import auth, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
