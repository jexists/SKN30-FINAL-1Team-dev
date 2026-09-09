"""사업자등록증 PDF·이미지 OCR 및 원본 보관 API."""

from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select

from app.api.deps import CurrentMember, DbSession
from app.core.config import settings
from app.models.content import Document
from app.models.content import File as FileRow
from app.models.crm import CustomerCompany
from app.schemas.business_licenses import BusinessLicenseScanAccepted, BusinessLicenseScanStatus
from app.schemas.documents import DocumentRead
from app.services import business_license_scans, storage
from app.services.agent_logging import log_agent_event
from app.services.storage import StorageError
from app.services.upload_guard import (
    AllowedMediaType,
    AllowedType,
    UploadRejected,
    check_image_upload,
    check_size,
    check_upload,
)

router = APIRouter(tags=["business-licenses"])


def _check_license_upload(
    *,
    file_name: str,
    declared_media_type: str | None,
    content: bytes,
) -> AllowedType | AllowedMediaType:
    """등록증은 PDF 와 사진을 함께 받는다. 인식과 보관이 같은 기준으로 막는다."""
    check_size(len(content), settings.business_card_max_bytes)
    extension = Path(file_name).suffix.lower()
    if extension == ".pdf":
        return check_upload(
            file_name=file_name,
            declared_media_type=declared_media_type,
            content=content,
        )
    if extension in {".png", ".jpg", ".jpeg", ".webp"}:
        return check_image_upload(
            file_name=file_name,
            declared_media_type=declared_media_type,
            content=content,
        )
    raise UploadRejected("business_license_unsupported_file", 415)


@router.post(
    "/business-licenses/scan",
    response_model=BusinessLicenseScanAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def scan_business_license(
    background: BackgroundTasks,
    member: CurrentMember,
    file: Annotated[UploadFile, File()],
) -> BusinessLicenseScanAccepted:
    """사업자등록증 인식을 접수하고 결과 조회용 scan_id를 돌려준다."""

    file_name = file.filename or "business-license"
    content = await file.read(settings.business_card_max_bytes + 1)
    try:
        allowed = _check_license_upload(
            file_name=file_name,
            declared_media_type=file.content_type,
            content=content,
        )
    except UploadRejected as rejected:
        raise HTTPException(status_code=rejected.status_code, detail=rejected.detail) from rejected

    if not settings.ocr_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ocr_not_configured",
        )

    scan_id = business_license_scans.create(member_id=member.id)
    log_agent_event(
        "business_license_scan_accepted",
        run_id=str(scan_id),
        agent_code=business_license_scans.AGENT_CODE,
    )
    background.add_task(
        business_license_scans.run,
        scan_id,
        file_name=file_name,
        media_type=allowed.media_type,
        content=content,
    )
    return BusinessLicenseScanAccepted(scan_id=scan_id, processing_status="processing")


@router.get(
    "/business-licenses/scan/{scan_id}",
    response_model=BusinessLicenseScanStatus,
)
async def get_business_license_scan(
    scan_id: UUID,
    member: CurrentMember,
) -> BusinessLicenseScanStatus:
    """접수한 본인의 사업자등록증 인식 상태를 반환한다."""

    state = business_license_scans.get(scan_id, member_id=member.id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="business_license_scan_not_found",
        )
    draft = state.draft
    return BusinessLicenseScanStatus(
        processing_status=state.processing_status,
        processing_error=state.processing_error,
        fields=draft.fields if draft is not None else None,
        missing_required_fields=draft.missing_required_fields if draft is not None else [],
        ready_for_company_registration=(
            draft.ready_for_company_registration if draft is not None else False
        ),
    )


@router.post(
    "/business-licenses/archive",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def archive_business_license(
    response: Response,
    company_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File()],
    member: CurrentMember,
    db: DbSession,
) -> DocumentRead:
    """등록된 고객사에 사업자등록증 원본을 연결해 보관한다.

    등록증은 사람이 아니라 회사의 문서다. 담당자가 아니라 회사에 묶어 두면 같은 회사의
    담당자 상세가 모두 같은 원본을 보고, 담당자마다 같은 파일이 쌓이지 않는다.
    """
    if not settings.storage_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="storage_not_configured",
        )

    file_name = file.filename or "business-license"
    content = await file.read(settings.business_card_max_bytes + 1)
    try:
        allowed = _check_license_upload(
            file_name=file_name,
            declared_media_type=file.content_type,
            content=content,
        )
    except UploadRejected as rejected:
        raise HTTPException(status_code=rejected.status_code, detail=rejected.detail) from rejected

    company = (
        await db.execute(
            select(CustomerCompany).where(
                CustomerCompany.id == company_id,
                CustomerCompany.team_id == member.team_id,
            )
        )
    ).scalar_one_or_none()
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="customer_company_not_found",
        )

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

    document_id = uuid4()
    try:
        # 문서번호 생성은 기존 자료실 규칙을 재사용하고, 여기서는 고객사 연결만 추가한다.
        from app.api.documents import _detail, _next_document_no

        db.add(
            Document(
                id=document_id,
                team_id=member.team_id,
                created_by_member_id=member.id,
                document_no=await _next_document_no(db, member, datetime.now().year),
                category_code="business_license",
                title=f"{company.name} 사업자등록증",
                description="사업자등록증 등록 시 보관된 원본",
                customer_company_id=company.id,
                tags=["business_license", "archive"],
            )
        )
        db.add(
            FileRow(
                id=uuid4(),
                report_id=None,
                document_id=document_id,
                # 명함 보관본과 같다. 버전은 관리하지 않지만 DB 검사가 1 이상을 요구한다.
                version_no=1,
                file_name=file_name.strip(),
                storage_key=storage_key,
                media_type=allowed.media_type,
                byte_size=len(content),
                processing_status="uploaded",
                extracted_text=None,
                uploaded_by_member_id=member.id,
                note="사업자등록증 원본",
            )
        )
        await db.commit()
        read = await _detail(db, member, document_id)
    except Exception:
        await db.rollback()
        await storage.remove(storage_key=storage_key)
        raise

    response.headers["Location"] = f"/api/documents/{document_id}"
    return read
