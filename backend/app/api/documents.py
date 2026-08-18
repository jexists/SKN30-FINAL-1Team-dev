from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import CurrentMember, DbSession
from app.core.config import settings
from app.models.content import Document
from app.models.content import File as FileRow
from app.models.crm import CustomerCompany
from app.models.sales import PurchaseOrder, SalesDeal
from app.models.workspace import Member, Team
from app.schemas.documents import (
    DocumentCreate,
    DocumentFileRead,
    DocumentPage,
    DocumentPageParams,
    DocumentPatch,
    DocumentRead,
    DownloadRead,
)
from app.services import storage
from app.services.storage import StorageError
from app.services.upload_guard import UploadRejected, check_size, check_upload

router = APIRouter(tags=["documents"])

_SEOUL = ZoneInfo("Asia/Seoul")
_creator = aliased(Member)
_company = aliased(CustomerCompany)
_uploader = aliased(Member)

DOWNLOAD_EXPIRES_IN = 60


def _contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _seoul(value: datetime) -> datetime:
    return value.astimezone(_SEOUL)


def _require_storage() -> None:
    if not settings.storage_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="storage_not_configured",
        )


def _joined_select(*entities):
    return (
        select(*entities)
        .select_from(Document)
        .join(_creator, Document.created_by_member_id == _creator.id)
        .outerjoin(_company, Document.customer_company_id == _company.id)
    )


def _scope(member: Member, creator_ids: tuple[UUID, ...] | None = None):
    """자료실은 팀 공유물이다. 팀원도 같은 팀 문서를 모두 본다."""
    conditions = [
        Document.team_id == member.team_id,
        _creator.team_id == member.team_id,
        or_(Document.customer_company_id.is_(None), _company.team_id == member.team_id),
    ]
    if creator_ids is not None:
        conditions.append(Document.created_by_member_id.in_(creator_ids))
    return conditions


def _file_read(row: FileRow, uploader_display_name: str) -> DocumentFileRead:
    return DocumentFileRead(
        id=row.id,
        version_no=row.version_no,
        file_name=row.file_name,
        media_type=row.media_type,
        byte_size=row.byte_size,
        processing_status=row.processing_status,
        uploaded_by_member_id=row.uploaded_by_member_id,
        uploaded_by_display_name=uploader_display_name,
        note=row.note,
        uploaded_at=_seoul(row.uploaded_at),
    )


def _document_read(
    document: Document,
    created_by_display_name: str,
    company_name: str | None,
    files: list[DocumentFileRead],
) -> DocumentRead:
    return DocumentRead(
        id=document.id,
        document_no=document.document_no,
        category_code=document.category_code,
        title=document.title,
        description=document.description,
        customer_company_id=document.customer_company_id,
        customer_company_name=company_name,
        sales_deal_id=document.sales_deal_id,
        purchase_order_id=document.purchase_order_id,
        tags=list(document.tags or ()),
        created_by_member_id=document.created_by_member_id,
        created_by_display_name=created_by_display_name,
        created_at=_seoul(document.created_at),
        files=files,
        latest_version_no=max((f.version_no for f in files), default=None),
    )


async def _files_by_document_ids(
    db: AsyncSession,
    document_ids: list[UUID],
) -> dict[UUID, list[DocumentFileRead]]:
    grouped: dict[UUID, list[DocumentFileRead]] = {doc_id: [] for doc_id in document_ids}
    if not document_ids:
        return grouped
    result = await db.execute(
        select(FileRow, _uploader.display_name)
        .join(_uploader, FileRow.uploaded_by_member_id == _uploader.id)
        .where(FileRow.document_id.in_(document_ids))
        .order_by(FileRow.version_no.desc())
    )
    for row, uploader_name in result.all():
        grouped[row.document_id].append(_file_read(row, uploader_name))
    return grouped


async def _document_row(db: AsyncSession, member: Member, document_id: UUID):
    result = await db.execute(
        _joined_select(Document, _creator.display_name, _company.name).where(
            Document.id == document_id, *_scope(member)
        )
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="document_not_found",
        )
    return row


async def _detail(db: AsyncSession, member: Member, document_id: UUID) -> DocumentRead:
    row = await _document_row(db, member, document_id)
    files = await _files_by_document_ids(db, [document_id])
    return _document_read(*row, files[document_id])


async def _validate_links(db: AsyncSession, member: Member, values: dict) -> None:
    """다른 팀 FK 를 붙이지 못하게 막는다. 존재 여부는 404 로 숨긴다."""
    checks = (
        ("customer_company_id", CustomerCompany, "customer_company_not_found"),
        ("sales_deal_id", SalesDeal, "sales_deal_not_found"),
        ("purchase_order_id", PurchaseOrder, "purchase_order_not_found"),
    )
    for field_name, model, detail in checks:
        target_id = values.get(field_name)
        if target_id is None:
            continue
        found = (
            await db.execute(
                select(model.id).where(model.id == target_id, model.team_id == member.team_id)
            )
        ).scalar_one_or_none()
        if found is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


async def _next_document_no(db: AsyncSession, member: Member, year: int) -> str:
    team_result = await db.execute(
        select(Team.id).where(Team.id == member.team_id).with_for_update(of=Team)
    )
    if team_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="team_not_found")

    prefix = f"SL-DC-{year}-"
    numbers_result = await db.execute(
        select(Document.document_no).where(
            Document.team_id == member.team_id,
            Document.document_no.like(f"{prefix}%"),
        )
    )
    numbers = []
    for document_no in numbers_result.scalars().all():
        suffix = document_no.removeprefix(prefix)
        if len(suffix) == 4 and suffix.isascii() and suffix.isdigit():
            numbers.append(int(suffix))
    next_number = max(numbers, default=0) + 1
    if next_number > 9_999:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="document_number_exhausted",
        )
    return f"{prefix}{next_number:04d}"


@router.get("/documents", response_model=DocumentPage)
async def list_documents(
    page: Annotated[DocumentPageParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> DocumentPage:
    creator_ids = (
        None
        if page.created_by_member_id is None
        else tuple(dict.fromkeys(page.created_by_member_id))
    )
    scope = _scope(member, creator_ids)
    if page.category_code is not None:
        scope.append(Document.category_code.in_(tuple(dict.fromkeys(page.category_code))))
    if page.customer_company_id is not None:
        scope.append(Document.customer_company_id == page.customer_company_id)
    if page.sales_deal_id is not None:
        scope.append(Document.sales_deal_id == page.sales_deal_id)
    if page.q is not None:
        pattern = _contains(page.q)
        scope.append(
            or_(
                Document.title.ilike(pattern, escape="\\"),
                Document.description.ilike(pattern, escape="\\"),
                Document.document_no.ilike(pattern, escape="\\"),
                _company.name.ilike(pattern, escape="\\"),
            )
        )

    total = (await db.execute(_joined_select(func.count(Document.id)).where(*scope))).scalar_one()
    rows = (
        await db.execute(
            _joined_select(Document, _creator.display_name, _company.name)
            .where(*scope)
            .order_by(Document.created_at.desc(), Document.id)
            .offset(page.skip)
            .limit(page.limit)
        )
    ).all()
    file_map = await _files_by_document_ids(db, [row[0].id for row in rows])
    items = [_document_read(*row, file_map[row[0].id]) for row in rows]
    has_more = page.skip + len(items) < total
    return DocumentPage(
        items=items,
        skip=page.skip,
        limit=page.limit,
        total=total,
        has_more=has_more,
        next_skip=page.skip + len(items) if has_more else None,
    )


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> DocumentRead:
    return await _detail(db, member, document_id)


@router.post("/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def create_document(
    payload: DocumentCreate,
    response: Response,
    member: CurrentMember,
    db: DbSession,
) -> DocumentRead:
    try:
        values = payload.model_dump()
        await _validate_links(db, member, values)
        document = Document(
            id=uuid4(),
            team_id=member.team_id,
            created_by_member_id=member.id,
            document_no=await _next_document_no(db, member, datetime.now(_SEOUL).year),
            category_code=payload.category_code,
            title=payload.title,
            description=payload.description,
            customer_company_id=payload.customer_company_id,
            sales_deal_id=payload.sales_deal_id,
            purchase_order_id=payload.purchase_order_id,
            tags=payload.tags,
        )
        db.add(document)
        await db.flush()
        read = await _detail(db, member, document.id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    response.headers["Location"] = f"/api/documents/{document.id}"
    return read


@router.patch("/documents/{document_id}", response_model=DocumentRead)
async def update_document(
    document_id: UUID,
    payload: DocumentPatch,
    member: CurrentMember,
    db: DbSession,
) -> DocumentRead:
    try:
        document = (
            await db.execute(
                select(Document)
                .where(Document.id == document_id, Document.team_id == member.team_id)
                .with_for_update(of=Document)
            )
        ).scalar_one_or_none()
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="document_not_found",
            )
        values = payload.model_dump(exclude_unset=True)
        await _validate_links(db, member, values)
        for field_name, value in values.items():
            setattr(document, field_name, value)
        await db.flush()
        read = await _detail(db, member, document_id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return read


@router.post(
    "/documents/{document_id}/files",
    response_model=DocumentFileRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document_file(
    document_id: UUID,
    member: CurrentMember,
    db: DbSession,
    upload: Annotated[UploadFile, File()],
    note: Annotated[str | None, Form(max_length=5_000)] = None,
) -> DocumentFileRead:
    _require_storage()
    content = await upload.read()

    try:
        check_size(len(content), settings.upload_max_bytes)
        allowed = check_upload(
            file_name=upload.filename or "",
            declared_media_type=upload.content_type,
            content=content,
        )
    except UploadRejected as rejected:
        raise HTTPException(
            status_code=rejected.status_code,
            detail=rejected.detail,
        ) from rejected

    storage_key = storage.build_storage_key(member.team_id, allowed.extension)
    try:
        await storage.upload(
            storage_key=storage_key,
            content=content,
            media_type=allowed.media_type,
        )
    except StorageError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    try:
        # 버전 번호는 서버가 트랜잭션 안에서 매긴다.
        document = (
            await db.execute(
                select(Document)
                .where(Document.id == document_id, Document.team_id == member.team_id)
                .with_for_update(of=Document)
            )
        ).scalar_one_or_none()
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="document_not_found",
            )
        current = (
            await db.execute(
                select(func.max(FileRow.version_no)).where(FileRow.document_id == document_id)
            )
        ).scalar_one()
        row = FileRow(
            id=uuid4(),
            report_id=None,
            document_id=document_id,
            version_no=(current or 0) + 1,
            file_name=(upload.filename or "").strip(),
            storage_key=storage_key,
            media_type=allowed.media_type,
            byte_size=len(content),
            processing_status="uploaded",
            extracted_text=None,
            uploaded_by_member_id=member.id,
            note=note,
        )
        db.add(row)
        await db.flush()
        read = _file_read(row, member.display_name)
        await db.commit()
    except Exception:
        await db.rollback()
        # DB 기록이 실패하면 올린 객체를 지워 고아를 남기지 않는다.
        await storage.remove(storage_key=storage_key)
        raise
    return read


@router.get("/documents/{document_id}/files/{file_id}/download", response_model=DownloadRead)
async def download_document_file(
    document_id: UUID,
    file_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> DownloadRead:
    _require_storage()
    # 다운로드마다 팀 권한을 다시 검사한다.
    await _document_row(db, member, document_id)
    row = (
        await db.execute(
            select(FileRow).where(FileRow.id == file_id, FileRow.document_id == document_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file_not_found")

    try:
        url = await storage.signed_url(
            storage_key=row.storage_key,
            expires_in=DOWNLOAD_EXPIRES_IN,
        )
    except StorageError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    return DownloadRead(
        url=url,
        expires_in=DOWNLOAD_EXPIRES_IN,
        file_name=row.file_name,
        media_type=row.media_type,
        byte_size=row.byte_size,
    )
