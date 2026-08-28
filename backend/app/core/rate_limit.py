"""IP 단위 시도 제한기.

로그인과 계정 요청이 같은 방식으로 무차별 시도를 막는다. 두 곳이 각자
dict 를 들고 있으면 만료 처리와 버킷 상한을 따로 고쳐야 해서 여기 한 벌만 둔다.

ponytail: 단일 프로세스용 고정 구간 제한기. 다중 worker 배포 시 공유 저장소로 교체한다.
"""

import math
import time


class AttemptLimiter:
    """키(보통 IP) 하나당 정해진 구간 안의 시도 횟수를 센다.

    제한값을 생성자가 아니라 reserve() 에서 받는다. 로그인 제한은 환경변수라
    실행 중에 바뀔 수 있어서, 값을 미리 붙들어 두면 바뀐 설정이 반영되지 않는다.
    """

    def __init__(self, *, max_buckets: int = 10_000) -> None:
        # key -> (구간 안에서 센 횟수, 구간이 시작된 시각)
        self._attempts: dict[str, tuple[int, float]] = {}
        self._max_buckets = max_buckets

    def reserve(self, key: str, *, max_attempts: int, window_seconds: int) -> int | None:
        """시도 한 칸을 잡는다.

        @returns 막혔으면 다시 시도해도 되기까지 남은 초, 통과했으면 None.
        """
        now = time.monotonic()
        expired_keys = [
            stale
            for stale, (_, started_at) in self._attempts.items()
            if now - started_at >= window_seconds
        ]
        for stale in expired_keys:
            self._attempts.pop(stale, None)

        count, started_at = self._attempts.get(key, (0, now))
        if count >= max_attempts:
            return max(1, math.ceil(window_seconds - (now - started_at)))
        # 버킷이 꽉 차면 새 키를 받지 않는다. 키를 바꿔 가며 메모리를 불리는 것도 시도다.
        if key not in self._attempts and len(self._attempts) + 1 > self._max_buckets:
            return window_seconds

        self._attempts[key] = (count + 1, started_at)
        return None

    def release(self, key: str) -> None:
        """잡아 둔 칸을 되돌린다. 사용자 잘못이 아닌 실패는 횟수로 세지 않는다."""
        attempt = self._attempts.get(key)
        if attempt is None:
            return
        count, started_at = attempt
        if count == 1:
            self._attempts.pop(key)
        else:
            self._attempts[key] = (count - 1, started_at)

    def clear(self) -> None:
        self._attempts.clear()

    def __len__(self) -> int:
        return len(self._attempts)
