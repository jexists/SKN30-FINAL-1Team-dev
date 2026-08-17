from fastapi import APIRouter

from app.api import activities, auth, customers, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(customers.router)
api_router.include_router(activities.router)
