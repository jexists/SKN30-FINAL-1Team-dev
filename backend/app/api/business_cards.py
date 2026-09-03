"""명함 이미지 OCR, 중복 확인 및 원본 보관 API."""

from datetime import datetime
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
from app.models.crm import CustomerCompany, CustomerContact
from app.schemas.business_cards import (
    BusinessCardFields,
    BusinessCardMatchRead,
    BusinessCardScanAccepted,
    BusinessCardScanStatus,
)
from app.schemas.documents import DocumentRead
from app.services import business_card_scans, business_cards, storage
from app.services.agent_logging import log_agent_event
from app.services.storage import StorageError
from app.services.upload_guard import UploadRejected, check_image_upload, check_size

router = APIRouter(tags=["business-cards"])


def _require_storage() -> None:
    if not settings.storage_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="storage_not_configured",
        )


@router.post("/business-cards/matches", response_model=list[BusinessCardMatchRead])
async def find_business_card_matches(
    fields: BusinessCardFields,
    member: CurrentMember,
    db: DbSession,
) -> list[BusinessCardMatchRead]:
    """명함 후보와 같은 팀의 기존 담당자를 비교한다. 자동 저장·병합은 하지 않는다."""
    matches = await business_cards.find_matches(db, member=member, fields=fields)
    return [BusinessCardMatchRead.model_validate(match) for match in matches]


@router.post(
    "/business-cards/scan",
    response_model=BusinessCardScanAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def scan_business_card(
    background: BackgroundTasks,
    member: CurrentMember,
    image: Annotated[UploadFile, File()],
) -> BusinessCardScanAccepted:
    """명함 인식을 접수하고 202 로 응답한다. 결과는 GET 으로 확인한다.

    OCR 과 LLM 을 동기로 기다리면 응답이 CloudFront origin timeout 을 넘겨 504 가
    된다. 업로드 검증만 여기서 끝내고 인식은 백그라운드로 넘긴다. 원본 이미지는
    저장하지 않고 작업 인자로만 전달한다.
    """
    content = await image.read(settings.business_card_max_bytes + 1)
    try:
        check_size(len(content), settings.business_card_max_bytes)
        allowed = check_image_upload(
            file_name=image.filename or "",
            declared_media_type=image.content_type,
            content=content,
        )
    except UploadRejected as rejected:
        raise HTTPException(status_code=rejected.status_code, detail=rejected.detail) from rejected

    if not settings.ocr_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ocr_not_configured",
        )
    scan_id = business_card_scans.create(member_id=member.id)
    # 요청이 서버까지 도달했다는 사실 자체가 업로드 실패와 인식 실패를 가른다.
    log_agent_event(
        "business_card_scan_accepted",
        run_id=str(scan_id),
        agent_code=business_card_scans.AGENT_CODE,
    )
    background.add_task(
        business_card_scans.run,
        scan_id,
        file_name=image.filename or "business-card",
        media_type=allowed.media_type,
        content=content,
    )
    return BusinessCardScanAccepted(scan_id=scan_id, processing_status="processing")


@router.get("/business-cards/scan/{scan_id}", response_model=BusinessCardScanStatus)
async def get_business_card_scan(
    scan_id: UUID,
    member: CurrentMember,
) -> BusinessCardScanStatus:
    """접수한 명함 인식의 진행 상태와 완료된 초안을 확인하는 폴링 대상."""
    state = business_card_scans.get(scan_id, member_id=member.id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="business_card_scan_not_found",
        )
    draft = state.draft
    return BusinessCardScanStatus(
        processing_status=state.processing_status,
        processing_error=state.processing_error,
        fields=draft.fields if draft is not None else None,
        missing_required_fields=draft.missing_required_fields if draft is not None else [],
        ready_for_contact_registration=(
            draft.ready_for_contact_registration if draft is not None else False
        ),
    )


@router.post(
    "/business-cards/archive",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def archive_business_card(
    response: Response,
    contact_id: Annotated[UUID, Form()],
    image: Annotated[UploadFile, File()],
    member: CurrentMember,
    db: DbSession,
) -> DocumentRead:
    """등록된 고객 담당자에 명함 원본을 연결해 자료실에 보관한다."""
    _require_storage()
    content = await image.read(settings.business_card_max_bytes + 1)
    try:
        check_size(len(content), settings.business_card_max_bytes)
        allowed = check_image_upload(
            file_name=image.filename or "",
            declared_media_type=image.content_type,
            content=content,
        )
    except UploadRejected as rejected:
        raise HTTPException(status_code=rejected.status_code, detail=rejected.detail) from rejected

    contact_row = (
        await db.execute(
            select(CustomerContact, CustomerCompany)
            .join(CustomerCompany, CustomerContact.company_id == CustomerCompany.id)
            .where(
                CustomerContact.id == contact_id,
                # 지운 고객에는 명함 원본을 새로 보관하지 않는다.
                CustomerContact.deleted_at.is_(None),
                CustomerCompany.team_id == member.team_id,
            )
        )
    ).one_or_none()
    if contact_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="customer_contact_not_found",
        )
    contact, _company = contact_row

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
        # 문서번호 생성은 기존 자료실 규칙을 재사용하고, 여기서는 고객 연결만 추가한다.
        from app.api.documents import _detail, _next_document_no

        document = Document(
            id=document_id,
            team_id=member.team_id,
            created_by_member_id=member.id,
            document_no=await _next_document_no(db, member, datetime.now().year),
            category_code="business_card",
            title=f"{contact.name} 명함",
            description="명함 등록 시 보관된 원본 이미지",
            customer_company_id=contact.company_id,
            customer_contact_id=contact.id,
            tags=["business_card", "archive"],
        )
        db.add(document)
        db.add(
            FileRow(
                id=uuid4(),
                report_id=None,
                document_id=document_id,
                version_no=1,
                file_name=(image.filename or "business-card").strip(),
                storage_key=storage_key,
                media_type=allowed.media_type,
                byte_size=len(content),
                processing_status="uploaded",
                extracted_text=None,
                uploaded_by_member_id=member.id,
                note="명함 원본 이미지",
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
