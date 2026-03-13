"""대시보드 데이터 조회/수정 엔드포인트."""

import settings  # noqa: F401  # sys.path/.env 초기화
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from tools.supabase_client import get_client

router = APIRouter()

ALLOWED_TABLES = {"videos", "runs", "analytics", "patterns"}
MAX_LIMIT = 500


class PatternUpdateRequest(BaseModel):
    is_active: bool


def _get_supabase_client():
    client = get_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Supabase 연결이 설정되지 않았습니다")
    return client


@router.get("/query")
async def query_table(
    table: str = Query(..., description="조회할 테이블"),
    select: str = Query("*", description="Supabase select 문"),
    order_column: str | None = Query(None, description="정렬 컬럼"),
    ascending: bool = Query(False, description="오름차순 여부"),
    filter_column: str | None = Query(None, description="eq 필터 컬럼"),
    filter_value: str | None = Query(None, description="eq 필터 값"),
    limit: int | None = Query(None, ge=1, le=MAX_LIMIT, description="최대 행 수"),
):
    if table not in ALLOWED_TABLES:
        raise HTTPException(status_code=400, detail=f"허용되지 않은 테이블입니다: {table}")
    if filter_column and filter_value is None:
        raise HTTPException(status_code=400, detail="filter_column 사용 시 filter_value가 필요합니다")

    client = _get_supabase_client()

    try:
        query = client.table(table).select(select)
        if filter_column and filter_value is not None:
            query = query.eq(filter_column, filter_value)
        if order_column:
            query = query.order(order_column, desc=not ascending)
        if limit:
            query = query.limit(limit)

        result = query.execute()
        return {"data": result.data or []}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/patterns/{pattern_id}")
async def update_pattern(pattern_id: str, req: PatternUpdateRequest):
    client = _get_supabase_client()

    try:
        result = (
            client.table("patterns")
            .update({"is_active": req.is_active})
            .eq("id", pattern_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not result.data:
        raise HTTPException(status_code=404, detail="패턴을 찾을 수 없습니다")

    return {"data": result.data[0]}
