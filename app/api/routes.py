"""API 路由聚合 — 导入所有子模块路由"""

from fastapi import APIRouter

from app.api.auth_routes import router as auth_router
from app.api.user_routes import router as user_router
from app.api.dept_routes import router as dept_router
from app.api.kb_routes import router as kb_router
from app.api.doc_routes import router as doc_router
from app.api.query_routes import router as query_router
from app.api.config_routes import router as config_router
from app.api.audit_routes import router as audit_router
from app.api.access_routes import router as access_router
from app.api.conversation_routes import router as conversation_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(user_router)
router.include_router(dept_router)
router.include_router(kb_router)
router.include_router(doc_router)
router.include_router(query_router)
router.include_router(config_router)
router.include_router(audit_router)
router.include_router(access_router)
router.include_router(conversation_router)
