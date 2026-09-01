"""명함 이미지 OCR, 중복 확인 및 원본 보관 API."""

from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentMember, DbSession
from app.core.config import settings
from app.models.content import Document
from app.models.content import File as FileRow
from app.models.crm import CustomerCompany, CustomerContact
from app.schemas.business_cards import BusinessCardDraft, BusinessCardFields, BusinessCardMatchRead
from app.schemas.documents import DocumentRead
from app.services import business_cards, ocr, storage
from app.services.llm import LLMError
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


@router.post("/business-cards/scan", response_model=BusinessCardDraft)
async def scan_business_card(
    _member: CurrentMember,
    image: Annotated[UploadFile, File()],
) -> BusinessCardDraft:
    """명함을 읽어 사용자 확인용 초안을 반환한다. 원본 이미지는 저장하지 않는다."""
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
    try:
        extracted = await ocr.extract_document(
            file_name=image.filename or "business-card",
            media_type=allowed.media_type,
            content=content,
            profile="business_card",
        )
        return await business_cards.extract(
            ocr_text=extracted.plain_text,
            file_name=image.filename or "business-card",
        )
    except ocr.OcrError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ocr_unavailable",
        ) from error
    except LLMError as error:
        detail = (
            "llm_not_configured"
            if str(error) == "llm_not_configured"
            else "business_card_extraction_failed"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        ) from error


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
