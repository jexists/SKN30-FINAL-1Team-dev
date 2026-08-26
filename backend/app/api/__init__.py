from fastapi import APIRouter

from app.api import (
    activities,
    admin,
    agent_runs,
    auth,
    business_cards,
    customers,
    dashboard,
    documents,
    health,
    members,
    notices,
    orders,
    reports,
    sales_deals,
    support,
    transcriptions,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(customers.router)
api_router.include_router(members.router)
api_router.include_router(activities.router)
api_router.include_router(sales_deals.router)
api_router.include_router(orders.router)
api_router.include_router(support.router)
api_router.include_router(reports.router)
api_router.include_router(notices.router)
api_router.include_router(agent_runs.router)
api_router.include_router(documents.router)
api_router.include_router(dashboard.router)
api_router.include_router(transcriptions.router)
api_router.include_router(business_cards.router)
api_router.include_router(admin.router)
