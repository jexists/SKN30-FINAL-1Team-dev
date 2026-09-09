import { useEffect, useRef, useState } from 'react'
import type { PDFDocumentLoadingTask, PDFDocumentProxy, RenderTask } from 'pdfjs-dist'

import Button from '@/components/Button'
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  MinusIcon,
  PlusIcon,
  RotateIcon,
} from '@/components/icons'

import styles from './SourceDocumentViewer.module.scss'

interface Props {
  /** OCR 에 쓴 원본. 이미지와 PDF 를 같은 껍데기 안에서 보여 줍니다. */
  file: File
  /** 오른쪽 패널을 접습니다. 접힌 상태는 부른 쪽이 들고 있습니다. */
  onCollapse: () => void
}

type Kind = 'image' | 'pdf'
type Status = 'loading' | 'ready' | 'error'

interface Size {
  width: number
  height: number
}

const ZOOM_MIN = 0.5
const ZOOM_MAX = 4
const ZOOM_STEP = 0.25
const EMPTY_SIZE: Size = { width: 0, height: 0 }

/**
 * 확장자와 MIME 을 함께 봅니다. 끌어다 놓은 파일은 type 이 비어 오는 일이 있어
 * businessLicense.ts 의 검사와 같은 기준을 씁니다.
 */
function documentKind(file: File): Kind {
  return file.type === 'application/pdf' || /\.pdf$/i.test(file.name) ? 'pdf' : 'image'
}

/** 90도 돌리면 가로세로가 바뀝니다. 패널에 맞출 배율은 돌아간 뒤 크기로 잽니다. */
function fitScale(content: Size, stage: Size, rotation: number): number {
  if (content.width === 0 || content.height === 0 || stage.width === 0) return 1
  const turned = rotation % 180 !== 0
  const width = turned ? content.height : content.width
  const height = turned ? content.width : content.height
  return Math.min(stage.width / width, stage.height / height)
}

export default function SourceDocumentViewer({ file, onCollapse }: Props) {
  const kind = documentKind(file)
  const stageRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  const [url, setUrl] = useState<string | null>(null)
  const [stage, setStage] = useState<Size>(EMPTY_SIZE)
  const [natural, setNatural] = useState<Size>(EMPTY_SIZE)
  const [zoom, setZoom] = useState(1)
  const [rotation, setRotation] = useState(0)
  const [page, setPage] = useState(1)
  const [pageCount, setPageCount] = useState(1)
  const [status, setStatus] = useState<Status>('loading')
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null)

  // 원본은 아직 서버에 올라가기 전이라 파일 그대로 브라우저 주소로 만들어 씁니다.
  useEffect(() => {
    const created = URL.createObjectURL(file)
    setUrl(created)
    setStatus('loading')
    setZoom(1)
    setRotation(0)
    setPage(1)
    setPageCount(1)
    setNatural(EMPTY_SIZE)
    return () => URL.revokeObjectURL(created)
  }, [file])

  // 패널을 접었다 펴거나 창을 줄이면 맞춤 배율이 달라집니다.
  useEffect(() => {
    const element = stageRef.current
    if (element === null) return

    const observer = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect
      if (box === undefined) return
      setStage((previous) =>
        Math.abs(previous.width - box.width) < 1 && Math.abs(previous.height - box.height) < 1
          ? previous
          : { width: box.width, height: box.height },
      )
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  // PDF 일 때만 pdf.js 를 받아 옵니다. 명함처럼 이미지만 다루는 흐름에서는
  // 이 청크가 아예 내려오지 않습니다.
  useEffect(() => {
    if (kind !== 'pdf' || url === null) return

    let cancelled = false
    let loading: PDFDocumentLoadingTask | null = null

    void (async () => {
      try {
        const pdfjs = await import('pdfjs-dist')
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          'pdfjs-dist/build/pdf.worker.min.mjs',
          import.meta.url,
        ).toString()
        loading = pdfjs.getDocument({ url })
        const opened = await loading.promise
        if (cancelled) return
        setPdf(opened)
        setPageCount(opened.numPages)
        setStatus('ready')
      } catch {
        if (!cancelled) setStatus('error')
      }
    })()

    return () => {
      cancelled = true
      setPdf(null)
      // 문서와 워커는 읽기 작업에 함께 딸려 있어 여기서 한 번에 정리됩니다.
      void loading?.destroy()
    }
  }, [kind, url])

  // 페이지·배율·회전이 바뀔 때마다 다시 그립니다. 앞선 렌더가 아직 돌고 있으면
  // 취소해야 캔버스에 두 페이지가 겹쳐 남지 않습니다.
  useEffect(() => {
    const canvas = canvasRef.current
    if (pdf === null || canvas === null || stage.width === 0) return

    let cancelled = false
    let task: RenderTask | null = null

    void (async () => {
      try {
        const target = await pdf.getPage(page)
        if (cancelled) return

        // 회전은 pdf.js 가 뷰포트에서 처리합니다. 맞춤 배율은 그 결과 크기로 잽니다.
        const turned = target.getViewport({ scale: 1, rotation })
        const scale = fitScale({ width: turned.width, height: turned.height }, stage, 0) * zoom
        const viewport = target.getViewport({ scale, rotation })
        // 캔버스는 화면 픽셀 밀도만큼 크게 잡고 CSS 로 줄여야 글자가 또렷합니다.
        const ratio = window.devicePixelRatio || 1
        canvas.width = Math.floor(viewport.width * ratio)
        canvas.height = Math.floor(viewport.height * ratio)
        canvas.style.width = `${Math.floor(viewport.width)}px`
        canvas.style.height = `${Math.floor(viewport.height)}px`

        task = target.render({
          canvas,
          viewport,
          transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
        })
        await task.promise
      } catch {
        // 취소된 렌더도 여기로 옵니다. 곧 다음 렌더가 이어지므로 알리지 않습니다.
      }
    })()

    return () => {
      cancelled = true
      task?.cancel()
    }
  }, [pdf, page, zoom, rotation, stage])

  const scale = fitScale(natural, stage, rotation) * zoom
  const turned = rotation % 180 !== 0
  const boxWidth = (turned ? natural.height : natural.width) * scale
  const boxHeight = (turned ? natural.width : natural.height) * scale

  const zoomBy = (step: number) =>
    setZoom((previous) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, previous + step)))

  return (
    <section className={styles.viewer} aria-label="원본 문서">
      <header className={styles.head}>
        <h3>원본 문서</h3>
        <span className={styles.fileName} title={file.name}>
          {file.name}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          iconOnly
          aria-label="원본 문서 접기"
          onClick={onCollapse}
        >
          <ChevronRightIcon />
        </Button>
      </header>

      <div className={styles.stage} ref={stageRef}>
        {status === 'error' ? (
          <p className={styles.notice}>원본을 미리 볼 수 없습니다. 파일은 그대로 보관됩니다.</p>
        ) : kind === 'pdf' ? (
          <canvas className={styles.canvas} ref={canvasRef} />
        ) : (
          url !== null && (
            <div className={styles.frame} style={{ width: boxWidth, height: boxHeight }}>
              <img
                className={styles.image}
                src={url}
                alt={`인식에 사용한 원본 ${file.name}`}
                style={{
                  width: natural.width * scale,
                  height: natural.height * scale,
                  transform: `rotate(${rotation}deg)`,
                }}
                onLoad={(event) => {
                  const image = event.currentTarget
                  setNatural({ width: image.naturalWidth, height: image.naturalHeight })
                  setStatus('ready')
                }}
                onError={() => setStatus('error')}
              />
            </div>
          )
        )}
        {status === 'loading' && <p className={styles.notice}>원본을 여는 중…</p>}
      </div>

      <div className={styles.toolbar}>
        <div className={styles.group}>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            iconOnly
            aria-label="축소"
            disabled={zoom <= ZOOM_MIN}
            onClick={() => zoomBy(-ZOOM_STEP)}
          >
            <MinusIcon />
          </Button>
          <button
            type="button"
            className={styles.zoomLabel}
            title="화면에 맞추기"
            onClick={() => setZoom(1)}
          >
            {Math.round(zoom * 100)}%
          </button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            iconOnly
            aria-label="확대"
            disabled={zoom >= ZOOM_MAX}
            onClick={() => zoomBy(ZOOM_STEP)}
          >
            <PlusIcon />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            iconOnly
            aria-label="90도 회전"
            onClick={() => setRotation((previous) => (previous + 90) % 360)}
          >
            <RotateIcon />
          </Button>
        </div>

        {/* 여러 장짜리 PDF 일 때만 나옵니다. 이미지와 한 장짜리에는 넘길 곳이 없습니다. */}
        {pageCount > 1 && (
          <div className={styles.group}>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              iconOnly
              aria-label="이전 페이지"
              disabled={page <= 1}
              onClick={() => setPage((previous) => Math.max(1, previous - 1))}
            >
              <ChevronLeftIcon />
            </Button>
            <span className={styles.pageLabel} aria-live="polite">
              {page} / {pageCount}
            </span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              iconOnly
              aria-label="다음 페이지"
              disabled={page >= pageCount}
              onClick={() => setPage((previous) => Math.min(pageCount, previous + 1))}
            >
              <ChevronRightIcon />
            </Button>
          </div>
        )}
      </div>
    </section>
  )
}
