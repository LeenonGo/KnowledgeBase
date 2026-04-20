# 架构重构进度跟踪

## P0 — 安全 & 数据完整性 ✅
- [x] 1. JWT Secret 外置到 .env
- [x] 2. 数据库密码外置到 .env
- [x] 3. CORS 按 APP_ENV 区分（生产限定域名）
- [x] 4. ID 生成改为 nanoid(21字符)
- [x] 5. Document 表 (kb_id, filename) 联合唯一约束

## P1 — 可维护性 & 功能完整性 ✅
- [x] 6. 后端路由拆分（10个模块，39条路由）
- [x] 7. 前端拆分 + hash 路由（10个页面模块 + router/api/ui 核心）
- [x] 8. 对话历史接入数据库（conversation_routes.py）
- [x] 9. 用户反馈(QAFeedback)接入（feedback API）
- [x] 10. 权限逻辑修通(KBUserAccess，同时支持部门+个人授权)

## P2 — 数据质量 ✅
- [x] 11. KBDepartmentAccess/KBUserAccess 补索引
- [x] 12. 统一错误处理 + 结构化日志（全局异常处理 + 请求日志中间件）
- [x] 13. 文件上传去重检测(file_hash)

## P3 — 扩展性
- [x] 14. Chroma 按 KB 分 collection（含自动迁移逻辑）
- [ ] 15. 配置迁移到数据库（多实例部署时再做）
