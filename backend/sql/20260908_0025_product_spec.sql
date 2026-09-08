-- 상품에 규격을 더한다.
--
-- 지금까지 product.memo 한 칸에 제품에 관한 말을 모두 적어 왔다. 규격을 따로 적게
-- 되면서 spec 을 더하고, memo 는 그대로 두어 비고로 쓴다. 화면이 부르는 이름만
-- "메모"에서 "비고"로 바뀌므로 기존 값은 옮기지 않는다.
--
-- 더하기만 하므로 아직 물러나지 않은 구코드도 깨지지 않는다. 적용 순서는 자유다.

BEGIN;

ALTER TABLE public.product ADD COLUMN spec text;

COMMENT ON COLUMN public.product.spec IS
    '제품 규격. 모델의 사양을 적는다. 없으면 NULL.';
COMMENT ON COLUMN public.product.memo IS
    '비고. 규격에 담기지 않는 참고 사항을 적는다. 화면에는 "비고"로 나온다. 없으면 NULL.';

COMMIT;
