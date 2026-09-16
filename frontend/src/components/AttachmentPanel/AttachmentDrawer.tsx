// 미팅 원문에 넣은 파일 하나를 자세히 보는 자리입니다.
// 목록은 훑는 곳이라 한 줄만 보여 주고, 원본 확인과 추출 텍스트 교정은 전부 여기서 합니다.
// 그림·PDF는 둘을 쌓으면 서로 자리를 뺏으므로 탭으로 갈라 각자 서랍 높이를 다 씁니다.
// 음성은 재생 막대 한 줄이라 뺏을 자리가 없어, 탭 없이 한자리에 쌓아 보여 줍니다.
import { useEffect, useState } from 'react'

import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import ImageLightbox from '@/components/ImageLightbox'
import { InlineLoader } from '@/components/Skeleton'
import Tabs from '@/components/Tabs'
import { CheckIcon, EditIcon } from '@/components/icons'
import type { ReportAttachment } from '@/types'
import { sizeLabel } from '@/utils/attachment'

import { EXTRACT_LABEL } from './extractLabel'

import styles from './AttachmentDrawer.module.scss'

interface Props {
  item: ReportAttachment
  /** 잠긴 화면. 원본과 추출된 텍스트는 그대로 보여 주고 교정만 걷습니다. */
  readOnly?: boolean
  /**
   * 원본을 가리키는 주소. 작성 화면은 올린 파일의 objectURL 이고,
   * 저장된 보고서는 판이 서버에서 받아 만든 주소입니다.
   */
  originalUrl?: string
  /** 저장된 보고서의 원본을 아직 받아오는 중. 탭이 뒤늦게 생겨 튀지 않게 자리를 먼저 잡습니다. */
  originalPending?: boolean
  /** 저장된 원본 내려받기. 완료 화면에만 있습니다. */
  onDownload?: () => void
  onExtractChange?: (id: string, extract: string) => void
  onClose: () => void
}

type Tab = 'original' | 'extract'

/** 원본 탭 이름은 파일 종류마다 하는 일이 달라 문구도 다릅니다. */
const ORIGINAL_LABEL: Record<ReportAttachment['kind'], string> = {
  audio: '원본 다시 듣기',
  image: '원본',
  pdf: '참고 화면',
}

export default function AttachmentDrawer({
  item,
  readOnly = false,
  originalUrl,
  originalPending = false,
  onDownload,
  onExtractChange,
  onClose,
}: Props) {
  // 복구된 초안은 원본 파일을 다시 들고 있지 않습니다. 열 수 없는 탭을 남겨 두면
  // 눌러 보고서야 알게 되므로, 그럴 때는 추출된 텍스트만 둡니다.
  // 판이 주소를 내려 주지만, 드로어만 따로 세우는 자리에서는 올린 파일의 주소를 그대로 씁니다.
  const source = originalUrl ?? item.previewUrl
  const hasOriginal = Boolean(source) || originalPending
  const stacked = hasOriginal && item.kind === 'audio'
  const [tab, setTab] = useState<Tab>(hasOriginal ? 'original' : 'extract')
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(item.extract ?? '')
  const [full, setFull] = useState(false)

  // 다른 파일로 갈아타면 교정 중이던 초안을 들고 가지 않습니다.
  useEffect(() => {
    setTab(hasOriginal ? 'original' : 'extract')
    setEditing(false)
    setDraft(item.extract ?? '')
    setFull(false)
  }, [item.id, item.extract, hasOriginal])

  const save = () => {
    onExtractChange?.(item.id, draft)
    setEditing(false)
  }

  const original = !source ? (
    <InlineLoader label={`${item.name} 원본 불러오는 중`} />
  ) : item.kind === 'audio' ? (
    <audio className={styles.audio} src={source} controls />
  ) : item.kind === 'image' ? (
    <button
      type="button"
      className={styles.imageButton}
      aria-label={`${item.name} 전체 화면으로 보기`}
      onClick={() => setFull(true)}
    >
      <img className={styles.image} src={source} alt={item.name} />
    </button>
  ) : (
    <iframe className={styles.pdf} src={source} title={`${item.name} 참고 화면`} />
  )

  return (
    <Drawer
      title={item.name}
      wide
      sub={
        <>
          {sizeLabel(item.byteSize)}
          {item.state === 'done' && Boolean(item.extract) && (
            <span className={styles.done}>
              {' · '}
              <CheckIcon width={12} height={12} />
              {EXTRACT_LABEL[item.kind]} 완료
            </span>
          )}
        </>
      }
      footer={onDownload && <Button onClick={onDownload}>다운로드</Button>}
      onClose={onClose}
    >
      {/* 열 원본이 없으면 탭 대신 왜 없는지 말합니다. 눌러 보고서야 알게 두지 않습니다. */}
      {!hasOriginal && (
        <p className={styles.missing}>
          {readOnly && !item.originalStored
            ? '원본 파일이 저장되지 않아 확인할 수 없습니다.'
            : '원본 파일을 다시 열 수 없습니다.'}
        </p>
      )}

      {hasOriginal && !stacked && (
        <Tabs
          items={[
            { value: 'original', label: ORIGINAL_LABEL[item.kind] },
            { value: 'extract', label: '추출된 텍스트' },
          ]}
          value={tab}
          onChange={setTab}
          label="첨부 보기 방식"
          variant="underline"
          className={styles.tabs}
        />
      )}

      {hasOriginal && (stacked || tab === 'original') && (
        <section className={styles.section}>{original}</section>
      )}

      {(stacked || tab === 'extract') && (
        <section className={styles.section}>
          <div className={styles.extractHead}>
            {!editing && !readOnly && (
              <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                <EditIcon width={14} height={14} />
                수정
              </Button>
            )}
          </div>

          {editing ? (
            <>
              <label className="sr-only" htmlFor={`extract-${item.id}`}>
                {item.name} 추출 텍스트 확인·수정
              </label>
              <textarea
                id={`extract-${item.id}`}
                className={styles.editor}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
              />
              <div className={styles.actions}>
                <Button
                  variant="outline"
                  onClick={() => {
                    setDraft(item.extract ?? '')
                    setEditing(false)
                  }}
                >
                  취소
                </Button>
                <Button onClick={save}>저장하기</Button>
              </div>
              <p className={styles.foot}>수정한 내용은 미팅 원문에 반영됩니다.</p>
            </>
          ) : (
            <p className={styles.extract}>{item.extract || '추출된 텍스트가 없습니다.'}</p>
          )}
        </section>
      )}

      {full && source && item.kind === 'image' && (
        <ImageLightbox
          src={source}
          alt={item.name}
          caption={`${item.name} · ${sizeLabel(item.byteSize)}`}
          onClose={() => setFull(false)}
        />
      )}
    </Drawer>
  )
}
