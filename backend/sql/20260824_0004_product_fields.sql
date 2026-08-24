-- 상품 마스터에 등록 화면이 받는 항목을 더한다.
--
-- 지금까지 product 는 이름 하나뿐이었고 행을 넣을 화면이 없어 seed 로만 만들었다.
-- 팀장이 /products 화면에서 직접 등록하게 되면서 분류·단가·유효기간·메모·사진이 붙는다.
--
-- 기존 행은 이름만 있으므로 백필용 default 로 채운 뒤 default 를 뗀다. 앱은 두 값을
-- 항상 함께 보내므로 DB 기본값에 기대지 않는다.

BEGIN;

ALTER TABLE public.product
    ADD COLUMN category_code text NOT NULL DEFAULT 'system'
        CHECK (category_code IN ('system', 'probe', 'consumable')),
    ADD COLUMN unit_price bigint NOT NULL DEFAULT 0 CHECK (unit_price >= 0),
    ADD COLUMN shelf_life_months integer
        CHECK (shelf_life_months IS NULL OR shelf_life_months > 0),
    ADD COLUMN memo text,
    ADD COLUMN image_storage_key text;

ALTER TABLE public.product ALTER COLUMN category_code DROP DEFAULT;
ALTER TABLE public.product ALTER COLUMN unit_price DROP DEFAULT;

COMMENT ON COLUMN public.product.category_code IS
    '제품 분류. system(시스템) / probe(프로브) / consumable(소모품).';
COMMENT ON COLUMN public.product.unit_price IS
    '제품 단가. 원 단위 정수로 저장한다. purchase_order_item.unit_price 와 같은 규칙이다.';
COMMENT ON COLUMN public.product.shelf_life_months IS
    '유효기간(개월). 로트별 만료일이 아니라 제품 자체의 기간이다. 없으면 NULL.';
COMMENT ON COLUMN public.product.image_storage_key IS
    '제품 사진의 저장소 객체 키. notice.image_storage_key 와 같은 뜻이며 응답에 내보내지 않는다.';

COMMIT;
