import { useEffect, useRef, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import Button from '@/components/Button'
import type { ContactOption } from '@/components/ContactPicker'
import Modal from '@/components/Modal'
import { SkeletonBlocks } from '@/components/Skeleton'
import SalesDealForm from '@/pages/Deals/SalesDealForm'
import {
  createSalesDealRecord,
  mutationErrorMessage,
  toColumn,
  type SalesDeal,
  type SalesDealColumn,
  type SalesDealSaveInput,
} from '@/pages/Deals/useSalesDeals'
import type { CustomerCompanyResponse, SalesPipelineResponse } from '@/types'
import type { SalesPipelineStageResponse } from '@/types'

interface Props {
  activityKey: string
  companyId: string
  contactId?: string | null
  contactName?: string
  fallbackContactName?: string
  onCreated: (deal: SalesDeal) => void
  onClose: () => void
}

interface LookupState {
  company: CustomerCompanyResponse | null
  pipeline: SalesPipelineResponse | null
  columns: SalesDealColumn[]
  loading: boolean
  error: string | null
}

const EMPTY_STATE: LookupState = {
  company: null,
  pipeline: null,
  columns: [],
  loading: true,
  error: null,
}

function lookupError(reason: unknown): string {
  if (reason instanceof Error && reason.message === 'published_pipeline_missing') {
    return '게시된 영업 파이프라인이 없어 새 딜을 만들 수 없습니다.'
  }
  if (reason instanceof Error && reason.message === 'pipeline_stage_missing') {
    return '게시된 영업 파이프라인에 생성 가능한 단계가 없어 새 딜을 만들 수 없습니다.'
  }
  return errorMessage(reason, '새 딜 선택지를 불러오지 못했습니다. 다시 시도해 주세요.')
}

export default function MeetingDealForm({
  activityKey,
  companyId,
  contactId,
  contactName,
  fallbackContactName,
  onCreated,
  onClose,
}: Props) {
  const [retryKey, setRetryKey] = useState(0)
  const [state, setState] = useState<LookupState>(EMPTY_STATE)
  const activeKey = `${activityKey}:${companyId}`
  const mountedKey = useRef(activeKey)

  useEffect(() => {
    mountedKey.current = activeKey
    return () => {
      if (mountedKey.current === activeKey) mountedKey.current = ''
    }
  }, [activeKey])

  useEffect(() => {
    const controller = new AbortController()
    let live = true
    setState({ ...EMPTY_STATE, loading: true })

    void Promise.all([
      client.get<CustomerCompanyResponse>(`/customer-companies/${companyId}`, {
        signal: controller.signal,
      }),
      client.get<SalesPipelineResponse[]>('/sales-pipelines', { signal: controller.signal }),
    ])
      .then(async ([companyResponse, pipelineResponse]) => {
        const pipeline =
          pipelineResponse.data.find(
            (item) => item.is_default && item.status_code === 'published',
          ) ?? pipelineResponse.data.find((item) => item.status_code === 'published')
        if (!pipeline) throw new Error('published_pipeline_missing')
        const { data: stages } = await client.get<SalesPipelineStageResponse[]>(
          `/sales-pipelines/${pipeline.id}/stages`,
          { signal: controller.signal },
        )
        if (stages.length === 0) throw new Error('pipeline_stage_missing')
        if (!live || mountedKey.current !== activeKey) return
        setState({
          company: companyResponse.data,
          pipeline,
          columns: stages.map(toColumn),
          loading: false,
          error: null,
        })
      })
      .catch((reason: unknown) => {
        if (!live || controller.signal.aborted || mountedKey.current !== activeKey) return
        setState({
          company: null,
          pipeline: null,
          columns: [],
          loading: false,
          error: lookupError(reason),
        })
      })

    return () => {
      live = false
      controller.abort()
    }
  }, [activeKey, companyId, retryKey])

  if (state.loading || state.error || !state.company || !state.pipeline) {
    return (
      <Modal
        title="새 딜 생성"
        onClose={onClose}
        footer={
          <>
            <Button type="button" variant="outline" onClick={onClose}>
              취소
            </Button>
            {state.error && (
              <Button type="button" onClick={() => setRetryKey((key) => key + 1)}>
                다시 시도
              </Button>
            )}
          </>
        }
      >
        {state.loading ? (
          <SkeletonBlocks label="새 딜 선택지를 불러오는 중입니다." count={3} height={48} />
        ) : (
          <p role="alert">{state.error}</p>
        )}
      </Modal>
    )
  }

  const initialContact: ContactOption | undefined = contactId
    ? {
        id: contactId,
        name: contactName?.trim() || fallbackContactName?.trim() || '담당자',
        companyId,
        org: state.company.name,
        dept: '',
        title: '',
      }
    : undefined

  const submit = async (input: SalesDealSaveInput) => {
    if (mountedKey.current !== activeKey) return
    if (input.customerCompanyId !== companyId) {
      throw new Error('미팅 회사와 다른 고객사를 선택할 수 없습니다.')
    }
    let data: SalesDeal
    try {
      data = await createSalesDealRecord(input, state.pipeline!.id)
    } catch (reason: unknown) {
      throw new Error(mutationErrorMessage(reason, '영업 딜을 등록'))
    }
    if (mountedKey.current === activeKey) onCreated(data)
  }

  return (
    <SalesDealForm
      columns={state.columns}
      initialCompany={state.company}
      initialContact={initialContact}
      onSubmit={submit}
      onClose={onClose}
    />
  )
}
