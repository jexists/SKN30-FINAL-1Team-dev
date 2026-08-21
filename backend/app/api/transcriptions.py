from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.api.deps import CurrentMember
from app.core.config import settings
from app.services import stt
from app.services.upload_guard import UploadRejected, check_audio_upload, check_size

router = APIRouter(tags=["transcriptions"])


class TranscriptionRead(BaseModel):
    transcript: str


@router.post("/transcriptions", response_model=TranscriptionRead)
async def create_transcription(
    _member: CurrentMember,
    audio: Annotated[UploadFile, File()],
) -> TranscriptionRead:
    # 제한보다 한 바이트만 더 읽어 대용량 파일을 메모리에 올리지 않고 413을 판정한다.
    content = await audio.read(settings.stt_max_bytes + 1)
    try:
        check_size(len(content), settings.stt_max_bytes)
        allowed = check_audio_upload(
            file_name=audio.filename or "",
            declared_media_type=audio.content_type,
            content=content,
        )
    except UploadRejected as rejected:
        raise HTTPException(status_code=rejected.status_code, detail=rejected.detail) from rejected

    try:
        transcript = await stt.transcribe(
            file_name=audio.filename or "",
            media_type=allowed.media_type,
            content=content,
        )
    except stt.STTNotConfigured as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="stt_not_configured",
        ) from error
    except stt.STTError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="stt_unavailable",
        ) from error

    return TranscriptionRead(transcript=transcript)
