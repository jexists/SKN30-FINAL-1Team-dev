/**
 * 업로드 전에 사진을 줄입니다.
 *
 * 명함 OCR 워커는 어차피 긴 변을 BUSINESS_CARD_MAX_SIDE(기본 2400px)로 줄인 뒤
 * 인식합니다. 그보다 큰 원본을 그대로 올리면 업로드 시간과 서버가 받는 base64
 * 크기만 늘고 인식 결과는 같습니다. 그래서 보내기 전에 같은 크기로 맞춥니다.
 *
 * 축소는 최적화입니다. 어느 단계에서 실패하든 원본을 그대로 돌려주고, 업로드
 * 자체를 막지 않습니다.
 */

/** 확장자를 .jpg 로 바꿉니다. 서버는 확장자·선언 MIME·signature 가 모두 맞아야 받습니다. */
function toJpegName(name: string): string {
  const dot = name.lastIndexOf('.')
  const base = dot > 0 ? name.slice(0, dot) : name
  return `${base}.jpg`
}

export async function downscaleImage(file: File, maxSide: number): Promise<File> {
  try {
    // EXIF 회전을 반영해 디코드합니다. 이 옵션이 없으면 세로로 찍은 명함이 눕습니다.
    const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
    try {
      const longest = Math.max(bitmap.width, bitmap.height)
      if (longest <= maxSide) return file

      const scale = maxSide / longest
      const width = Math.max(1, Math.round(bitmap.width * scale))
      const height = Math.max(1, Math.round(bitmap.height * scale))
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const context = canvas.getContext('2d')
      if (context === null) return file
      context.drawImage(bitmap, 0, 0, width, height)

      const blob = await new Promise<Blob | null>((resolve) => {
        canvas.toBlob(resolve, 'image/jpeg', 0.9)
      })
      if (blob === null || blob.size >= file.size) return file
      return new File([blob], toJpegName(file.name), {
        type: 'image/jpeg',
        lastModified: file.lastModified,
      })
    } finally {
      bitmap.close()
    }
  } catch {
    return file
  }
}
