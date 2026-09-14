-- 어드민 계정 발급(POST /admin/accounts)으로 만든 팀은 team 행만 생기고 팀별 룩업이
-- 비어 있어 고객 등록이 customer_contact_status_code_not_found(422)로 막힌다.
-- 기존 팀에 빠진 기본값을 채운다. 앞으로 만들 팀은 API가 직접 채운다.
--
-- id는 seed_demo_auth.configuration_id 와 같은 규칙(md5("<네임스페이스>:<테이블>:<코드>"))
-- 으로 만든다. 시드 스크립트를 나중에 같은 팀에 돌려도 같은 행을 가리키게 하기 위해서다.
-- 모든 INSERT 가 ON CONFLICT DO NOTHING 이라 여러 번 돌려도 안전하고, 팀이 직접 이름·색을
-- 바꿨거나 지운(deleted_at) 행은 건드리지 않는다.

BEGIN;

INSERT INTO public.customer_contact_status (id, team_id, code, name, tone, "position")
SELECT md5(t.id::text || ':customer_contact_status:' || d.code)::uuid,
       t.id, d.code, d.name, d.tone, d.position
FROM public.team t
CROSS JOIN (VALUES
    ('new', '신규', 'gray', 0),
    ('proposal', '제안', 'blue', 1),
    ('negotiation', '협의', 'orange', 2),
    ('contracted', '계약', 'green', 3),
    ('on_hold', '보류', 'red', 4)
) AS d(code, name, tone, position)
ON CONFLICT (team_id, code) DO NOTHING;

INSERT INTO public.activity_category (id, team_id, code, name, tone, "position")
SELECT md5(t.id::text || ':activity_category:' || d.code)::uuid,
       t.id, d.code, d.name, d.tone, d.position
FROM public.team t
CROSS JOIN (VALUES
    ('visit', '방문', 'blue', 0),
    ('demo', '데모', 'purple', 1),
    ('education', '교육', 'green', 2),
    ('call', '전화', 'gray', 3),
    ('delivery', '납품', 'orange', 4),
    ('conference', '컨퍼런스', 'purple', 5)
) AS d(code, name, tone, position)
ON CONFLICT (team_id, code) DO NOTHING;

INSERT INTO public.activity_action_tag (id, team_id, code, name, tone, "position")
SELECT md5(t.id::text || ':activity_action_tag:' || d.code)::uuid,
       t.id, d.code, d.name, d.tone, d.position
FROM public.team t
CROSS JOIN (VALUES
    ('first_call', '첫 전화', 'gray', 0),
    ('meeting', '미팅', 'blue', 1),
    ('demo_requested', '데모 요청', 'blue', 2),
    ('demo_in_progress', '데모 진행', 'purple', 3),
    ('demo_completed', '데모 완료', 'green', 4),
    ('quote_completed', '견적완료', 'purple', 5),
    ('contract_completed', '계약완료', 'green', 6),
    ('product_training', '제품교육', 'blue', 7),
    ('delivery_completed', '납품완료', 'green', 8),
    ('internal_meeting', '내부회의', 'gray', 9),
    ('conference', '컨퍼런스', 'purple', 10)
) AS d(code, name, tone, position)
ON CONFLICT (team_id, code) DO NOTHING;

INSERT INTO public.sales_deal_type (id, team_id, code, name, "position")
SELECT md5(t.id::text || ':sales_deal_type:' || d.code)::uuid,
       t.id, d.code, d.name, d.position
FROM public.team t
CROSS JOIN (VALUES
    ('new_installation', '신규 도입', 0),
    ('expansion', '증설', 1),
    ('renewal', '갱신', 2),
    ('maintenance', '유지보수', 3),
    ('consumables_supply', '소모품 공급', 4)
) AS d(code, name, position)
ON CONFLICT (team_id, code) DO NOTHING;

INSERT INTO public.purchase_order_status
    (id, team_id, code, name, tone, "position", outcome_code)
SELECT md5(t.id::text || ':purchase_order_status:' || d.code)::uuid,
       t.id, d.code, d.name, d.tone, d.position, d.outcome_code
FROM public.team t
CROSS JOIN (VALUES
    ('order_received', '발주 접수', 'gray', 0, 'in_progress'),
    ('dispatch_request_completed', '출고 의뢰서 완료', 'purple', 1, 'in_progress'),
    ('in_production', '생산중', 'orange', 2, 'in_progress'),
    ('stock_received', '입고 완료', 'blue', 3, 'in_progress'),
    ('delivered', '납품 완료', 'green', 4, 'completed'),
    ('cancelled', '발주취소', 'red', 5, 'cancelled')
) AS d(code, name, tone, position, outcome_code)
ON CONFLICT (team_id, code) DO NOTHING;

INSERT INTO public.quote_status (id, team_id, code, name, tone, "position", outcome_code)
SELECT md5(t.id::text || ':quote_status:' || d.code)::uuid,
       t.id, d.code, d.name, d.tone, d.position, d.outcome_code
FROM public.team t
CROSS JOIN (VALUES
    ('drafting', '견적작성', 'gray', 0, 'in_progress'),
    ('reviewing', '견적검토', 'blue', 1, 'in_progress'),
    ('sent', '고객발송', 'purple', 2, 'in_progress'),
    ('negotiating', '조건협의', 'orange', 3, 'in_progress'),
    ('completed', '견적완료', 'green', 4, 'completed')
) AS d(code, name, tone, position, outcome_code)
ON CONFLICT (team_id, code) DO NOTHING;

INSERT INTO public.contract_status (id, team_id, code, name, tone, "position", outcome_code)
SELECT md5(t.id::text || ':contract_status:' || d.code)::uuid,
       t.id, d.code, d.name, d.tone, d.position, d.outcome_code
FROM public.team t
CROSS JOIN (VALUES
    ('drafting', '초안작성', 'gray', 0, 'in_progress'),
    ('reviewing', '계약검토', 'blue', 1, 'in_progress'),
    ('negotiating', '고객협의', 'orange', 2, 'in_progress'),
    ('signed', '고객서명', 'purple', 3, 'in_progress'),
    ('completed', '계약완료', 'green', 4, 'completed')
) AS d(code, name, tone, position, outcome_code)
ON CONFLICT (team_id, code) DO NOTHING;

-- 기본 영업 파이프라인. 룩업이 다 있어도 이게 없으면 영업 기회 화면이 비어 버린다.
-- 이미 기본 파이프라인을 가진 팀은 건너뛴다.
INSERT INTO public.sales_pipeline
    (id, team_id, name, description, status_code, is_default, published_at, archived_at)
SELECT md5(t.id::text || ':sales_pipeline:default')::uuid,
       t.id, '기본 영업', NULL, 'published', true, now(), NULL
FROM public.team t
WHERE NOT EXISTS (
    SELECT 1 FROM public.sales_pipeline p
    WHERE p.team_id = t.id AND p.is_default AND p.status_code = 'published'
)
ON CONFLICT (team_id, name) DO NOTHING;

INSERT INTO public.sales_pipeline_stage
    (id, sales_pipeline_id, stage_code, name, tone, phase_code, outcome_code, "position")
SELECT md5(p.id::text || ':sales_pipeline_stage:' || d.stage_code)::uuid,
       p.id, d.stage_code, d.name, d.tone, d.phase_code, d.outcome_code, d.position
FROM public.sales_pipeline p
CROSS JOIN (VALUES
    ('needs_validation', '니즈 검증', 'gray', 'sales', 'in_progress', 0),
    ('product_demo', '제품 시연 평가', 'blue', 'sales', 'in_progress', 1),
    ('quote_sent', '견적서 발송', 'purple', 'quote', 'in_progress', 2),
    ('contract_sent', '계약서 발송', 'orange', 'contract', 'in_progress', 3),
    ('contract_review', '계약서 검토', 'orange', 'contract', 'in_progress', 4),
    ('contract_completed', '계약 완료', 'green', 'contract', 'confirmed', 5),
    ('order_in_progress', '발주 진행', 'purple', 'order', 'confirmed', 6),
    ('order_delivered', '납품 완료', 'green', 'order', 'confirmed', 7),
    ('closed_cancelled', '취소', 'red', 'closed', 'cancelled', 8)
) AS d(stage_code, name, tone, phase_code, outcome_code, position)
-- 단계를 하나라도 직접 손본 파이프라인은 position 유일 제약과 부딪히므로 건드리지 않는다.
WHERE NOT EXISTS (
    SELECT 1 FROM public.sales_pipeline_stage s WHERE s.sales_pipeline_id = p.id
)
ON CONFLICT (sales_pipeline_id, stage_code) DO NOTHING;

COMMIT;
