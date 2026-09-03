"""사업자등록증 PDF·이미지 OCR API."""

from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status

from app.api.deps import CurrentMember
from app.core.config import settings
from app.schemas.business_licenses import BusinessLicenseScanAccepted, BusinessLicenseScanStatus
from app.services import business_license_scans
from app.services.agent_logging import log_agent_event
from app.services.upload_guard import (
    UploadRejected,
    check_image_upload,
    check_size,
    check_upload,
)

router = APIRouter(tags=["business-licenses"])


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
    extension = Path(file_name).suffix.lower()
    content = await file.read(settings.business_card_max_bytes + 1)
    try:
        check_size(len(content), settings.business_card_max_bytes)
        if extension == ".pdf":
            allowed = check_upload(
                file_name=file_name,
                declared_media_type=file.content_type,
                content=content,
            )
        elif extension in {".png", ".jpg", ".jpeg", ".webp"}:
            allowed = check_image_upload(
                file_name=file_name,
                declared_media_type=file.content_type,
                content=content,
            )
        else:
            raise UploadRejected("business_license_unsupported_file", 415)
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
