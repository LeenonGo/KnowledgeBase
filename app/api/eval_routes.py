"""评测管理 API — 评测集生成、评测运行、结果查询"""

import json
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.models.models import (
    EvalDataset, EvalQuestion, EvalRun, EvalResult, KnowledgeBase, AuditLog,
)
from app.api.deps import get_current_user, log_audit, get_accessible_kb_ids

logger = logging.getLogger("kb.eval")
router = APIRouter(prefix="/api", tags=["评测"])


# ─── 后台任务：生成评测集 ─────────────────────────
def _bg_generate_questions(db_url: str, dataset_id: str, kb_id: str, count: int, user_id: str):
    """后台生成评测问题"""
    from app.core.database import engine
    from sqlalchemy.orm import Session as SASession
    from app.core.eval_generator import generate_questions

    with SASession(engine) as db:
        ds = db.query(EvalDataset).filter(EvalDataset.id == dataset_id).first()
        if not ds:
            return
        try:
            questions = generate_questions(kb_id=kb_id, count=count)
            for q in questions:
                eq = EvalQuestion(
                    dataset_id=dataset_id,
                    kb_id=kb_id,
                    question=q["question"],
                    expected_answer=q.get("answer", ""),
                    category=q["category"],
                    source_hint=q.get("source_hint", ""),
                    ref_chunks=json.dumps(q.get("ref_chunks", []), ensure_ascii=False),
                )
                db.add(eq)
            ds.question_count = len(questions)
            ds.status = "ready"
            db.commit()
            logger.info(f"评测集生成完成: dataset={dataset_id}, 问题数={len(questions)}")
        except Exception as e:
            logger.error(f"评测集生成失败: {e}", exc_info=True)
            ds.status = "error"
            db.commit()


# ─── 后台任务：执行评测 ─────────────────────────
def _bg_run_evaluation(db_url: str, run_id: str, dataset_id: str, kb_id: str, user_id: str):
    """后台执行评测"""
    from app.core.database import engine
    from sqlalchemy.orm import Session as SASession
    from app.core.eval_runner import run_single_evaluation

    with SASession(engine) as db:
        run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
        if not run:
            return
        try:
            questions = db.query(EvalQuestion).filter(
                EvalQuestion.dataset_id == dataset_id
            ).all()

            total = len(questions)
            passed_count = 0
            all_scores = []

            for eq in questions:
                ref_chunks = json.loads(eq.ref_chunks) if eq.ref_chunks else []
                try:
                    result = run_single_evaluation(
                        question=eq.question,
                        category=eq.category,
                        expected_answer=eq.expected_answer,
                        ref_chunks=ref_chunks,
                        kb_id=kb_id,
                    )
                except Exception as e:
                    logger.error(f"单题评测失败 q={eq.id}: {e}")
                    result = {
                        "retrieved_chunks": [],
                        "actual_answer": f"[评测失败: {e}]",
                        "scores": {},
                        "reasoning": f"执行异常: {e}",
                        "avg_score": 0.0,
                        "passed": False,
                        "latency_ms": 0,
                    }

                er = EvalResult(
                    run_id=run_id,
                    question_id=eq.id,
                    question=eq.question,
                    category=eq.category,
                    expected_answer=eq.expected_answer,
                    retrieved_chunks=json.dumps(result["retrieved_chunks"], ensure_ascii=False),
                    actual_answer=result["actual_answer"],
                    scores=json.dumps(result["scores"], ensure_ascii=False),
                    reasoning=result["reasoning"],
                    avg_score=result["avg_score"],
                    passed=result["passed"],
                    latency_ms=result["latency_ms"],
                )
                db.add(er)

                if result["passed"]:
                    passed_count += 1
                all_scores.append(result["avg_score"])

            run.total = total
            run.passed = passed_count
            run.failed = total - passed_count
            run.avg_score = round(sum(all_scores) / max(len(all_scores), 1), 3)
            run.status = "completed"
            _CST = timezone(timedelta(hours=8))
            run.finished_at = datetime.now(_CST)
            db.commit()
            logger.info(f"评测完成: run={run_id}, total={total}, passed={passed_count}, avg={run.avg_score}")

        except Exception as e:
            logger.error(f"评测运行失败: {e}", exc_info=True)
            run.status = "error"
            _CST = timezone(timedelta(hours=8))
            run.finished_at = datetime.now(_CST)
            db.commit()


# ─── API 路由 ─────────────────────────────────

@router.get("/eval/datasets")
async def list_eval_datasets(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """获取所有评测集列表"""
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="仅 super_admin 可访问")

    datasets = db.query(EvalDataset).order_by(EvalDataset.created_at.desc()).all()
    return [
        {
            "id": ds.id,
            "kb_id": ds.kb_id,
            "kb_name": ds.kb.name if ds.kb else "",
            "name": ds.name,
            "question_count": ds.question_count,
            "status": ds.status,
            "created_at": ds.created_at.isoformat() if ds.created_at else "",
        }
        for ds in datasets
    ]


@router.post("/eval/generate")
async def generate_eval_dataset(
    data: dict,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """为指定知识库生成评测集"""
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="仅 super_admin 可操作")

    kb_ids = data.get("kb_ids", [])
    count = data.get("count", 15)
    if not kb_ids:
        raise HTTPException(status_code=400, detail="请选择至少一个知识库")

    created = []
    for kb_id in kb_ids:
        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
        if not kb:
            continue

        ds = EvalDataset(
            kb_id=kb_id,
            name=f"{kb.name} - 评测集",
            question_count=0,
            status="generating",
            created_by=user.get("sub"),
        )
        db.add(ds)
        db.flush()

        from app.core.database import DATABASE_URL
        background_tasks.add_task(
            _bg_generate_questions, DATABASE_URL, ds.id, kb_id, count, user.get("sub")
        )
        created.append({"id": ds.id, "kb_name": kb.name})

    db.commit()

    log_audit(db, user, "eval_generate", "评测集", f"生成 {len(created)} 个评测集", "success",
              request.client.host if request.client else "")

    return {"message": f"已提交 {len(created)} 个评测集生成任务", "datasets": created}


@router.get("/eval/datasets/{dataset_id}/questions")
async def get_dataset_questions(
    dataset_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """获取评测集中的所有问题"""
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="仅 super_admin 可访问")

    questions = db.query(EvalQuestion).filter(
        EvalQuestion.dataset_id == dataset_id
    ).order_by(EvalQuestion.created_at).all()

    return [
        {
            "id": q.id,
            "question": q.question,
            "expected_answer": q.expected_answer,
            "category": q.category,
            "source_hint": q.source_hint,
            "ref_chunks": json.loads(q.ref_chunks) if q.ref_chunks else [],
        }
        for q in questions
    ]


@router.delete("/eval/datasets/{dataset_id}")
async def delete_eval_dataset(
    dataset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """删除评测集及其所有问题和运行结果"""
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="仅 super_admin 可操作")

    ds = db.query(EvalDataset).filter(EvalDataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="评测集不存在")

    db.delete(ds)
    db.commit()

    log_audit(db, user, "eval_delete", "评测集", f"删除评测集 {dataset_id}", "success",
              request.client.host if request.client else "")

    return {"message": "已删除"}


@router.post("/eval/datasets/{dataset_id}/questions/{question_id}")
async def update_eval_question(
    dataset_id: str,
    question_id: str,
    data: dict,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """编辑单个评测问题"""
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="仅 super_admin 可操作")

    q = db.query(EvalQuestion).filter(
        EvalQuestion.id == question_id,
        EvalQuestion.dataset_id == dataset_id,
    ).first()
    if not q:
        raise HTTPException(status_code=404, detail="问题不存在")

    if "question" in data:
        q.question = data["question"]
    if "expected_answer" in data:
        q.expected_answer = data["expected_answer"]
    if "category" in data:
        q.category = data["category"]

    db.commit()
    return {"message": "已更新"}


@router.delete("/eval/datasets/{dataset_id}/questions/{question_id}")
async def delete_eval_question(
    dataset_id: str,
    question_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """删除单个评测问题"""
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="仅 super_admin 可操作")

    q = db.query(EvalQuestion).filter(
        EvalQuestion.id == question_id,
        EvalQuestion.dataset_id == dataset_id,
    ).first()
    if not q:
        raise HTTPException(status_code=404, detail="问题不存在")

    db.delete(q)

    ds = db.query(EvalDataset).filter(EvalDataset.id == dataset_id).first()
    if ds:
        ds.question_count = max(0, ds.question_count - 1)

    db.commit()
    return {"message": "已删除"}


@router.post("/eval/run/{dataset_id}")
async def start_eval_run(
    dataset_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """启动评测运行"""
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="仅 super_admin 可操作")

    ds = db.query(EvalDataset).filter(EvalDataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="评测集不存在")
    if ds.status != "ready":
        raise HTTPException(status_code=400, detail=f"评测集状态为 {ds.status}，无法运行")

    # 检查是否有问题
    q_count = db.query(func.count(EvalQuestion.id)).filter(
        EvalQuestion.dataset_id == dataset_id
    ).scalar()
    if q_count == 0:
        raise HTTPException(status_code=400, detail="评测集中没有问题")

    run = EvalRun(
        dataset_id=dataset_id,
        kb_id=ds.kb_id,
        total=q_count,
        status="running",
        created_by=user.get("sub"),
    )
    db.add(run)
    db.flush()

    from app.core.database import DATABASE_URL
    background_tasks.add_task(
        _bg_run_evaluation, DATABASE_URL, run.id, dataset_id, ds.kb_id, user.get("sub")
    )

    db.commit()

    log_audit(db, user, "eval_run", "评测", f"启动评测 run={run.id}", "success",
              request.client.host if request.client else "")

    return {"message": "评测已启动", "run_id": run.id}


@router.get("/eval/runs")
async def list_eval_runs(
    dataset_id: str = None,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """获取评测运行记录"""
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="仅 super_admin 可访问")

    query = db.query(EvalRun).order_by(EvalRun.started_at.desc())
    if dataset_id:
        query = query.filter(EvalRun.dataset_id == dataset_id)

    runs = query.limit(50).all()
    return [
        {
            "id": r.id,
            "dataset_id": r.dataset_id,
            "kb_id": r.kb_id,
            "total": r.total,
            "passed": r.passed,
            "failed": r.failed,
            "avg_score": r.avg_score,
            "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else "",
            "finished_at": r.finished_at.isoformat() if r.finished_at else "",
        }
        for r in runs
    ]


# ─── 评测 Prompt 管理 ─────────────────────────────
from pathlib import Path

EVAL_PROMPTS_PATH = Path(__file__).parent.parent.parent / "config" / "eval_prompts.json"


@router.get("/config/eval-prompts")
async def get_eval_prompts(user: dict = Depends(get_current_user)):
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="仅 super_admin 可访问")
    if EVAL_PROMPTS_PATH.exists():
        with open(EVAL_PROMPTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


@router.post("/config/eval-prompts")
async def save_eval_prompts(data: dict, user: dict = Depends(get_current_user)):
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="仅 super_admin 可操作")
    EVAL_PROMPTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EVAL_PROMPTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    import app.core.eval_generator as eg
    eg._eval_prompts_cache = None
    eg._eval_prompts_mtime = 0
    return {"message": "评测 Prompt 已保存"}


@router.get("/eval/runs/{run_id}/results")
async def get_run_results(
    run_id: str,
    category: str = None,
    passed: bool = None,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """获取评测运行的详细结果"""
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="仅 super_admin 可访问")

    query = db.query(EvalResult).filter(EvalResult.run_id == run_id)

    if category:
        query = query.filter(EvalResult.category == category)
    if passed is not None:
        query = query.filter(EvalResult.passed == passed)

    results = query.order_by(EvalResult.avg_score).all()

    # 汇总统计
    run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="评测运行不存在")

    # 按类别统计
    all_results = db.query(EvalResult).filter(EvalResult.run_id == run_id).all()
    category_stats = {}
    dimension_scores = {}
    for r in all_results:
        cat = r.category
        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "passed": 0, "avg_score": 0, "scores": []}
        category_stats[cat]["total"] += 1
        if r.passed:
            category_stats[cat]["passed"] += 1
        category_stats[cat]["scores"].append(r.avg_score)

        scores = json.loads(r.scores) if r.scores else {}
        for dim, val in scores.items():
            if dim not in dimension_scores:
                dimension_scores[dim] = []
            dimension_scores[dim].append(val)

    for cat in category_stats:
        s = category_stats[cat]["scores"]
        category_stats[cat]["avg_score"] = round(sum(s) / max(len(s), 1), 3)
        del category_stats[cat]["scores"]

    dim_avgs = {d: round(sum(v) / len(v), 3) for d, v in dimension_scores.items()}

    return {
        "run": {
            "id": run.id,
            "total": run.total,
            "passed": run.passed,
            "failed": run.failed,
            "avg_score": run.avg_score,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else "",
            "finished_at": run.finished_at.isoformat() if run.finished_at else "",
        },
        "category_stats": category_stats,
        "dimension_scores": dim_avgs,
        "results": [
            {
                "id": r.id,
                "question": r.question,
                "category": r.category,
                "expected_answer": r.expected_answer,
                "retrieved_chunks": json.loads(r.retrieved_chunks) if r.retrieved_chunks else [],
                "actual_answer": r.actual_answer,
                "scores": json.loads(r.scores) if r.scores else {},
                "reasoning": r.reasoning,
                "avg_score": r.avg_score,
                "passed": r.passed,
                "latency_ms": r.latency_ms,
            }
            for r in results
        ],
    }
