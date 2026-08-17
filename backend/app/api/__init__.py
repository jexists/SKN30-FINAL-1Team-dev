from fastapi import APIRouter

from app.api import activities, auth, contracts, customers, health, orders, support

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(customers.router)
api_router.include_router(activities.router)
api_router.include_router(contracts.router)
api_router.include_router(orders.router)
api_router.include_router(support.router)
