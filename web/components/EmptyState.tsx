import type { ReactNode } from 'react';

/**
 * 결과가 없을 때 보여주는 상태.
 *
 * 이 프로젝트의 신뢰 정책상 "없으면 없다고 말한다"가 원칙이므로,
 * 비어 있는 이유를 학생이 구분할 수 있게 두 가지를 나눠서 표시한다.
 *  - degraded: 학교 정보를 불러오지 못한 것 (다시 시도하면 나올 수 있음)
 *  - 그 외: 실제로 해당하는 결과가 없는 것
 */
export default function EmptyState({
  degraded = false,
  message,
  hint,
}: {
  degraded?: boolean;
  message?: string;
  hint?: ReactNode;
}) {
  if (degraded) {
    return (
      <div className="empty">
        지금 학교 정보를 불러오지 못했어요.
        <div className="empty__hint">잠시 뒤에 다시 열어봐 주세요.</div>
      </div>
    );
  }

  return (
    <div className="empty">
      {message ?? '표시할 내용이 없어요.'}
      {hint ? <div className="empty__hint">{hint}</div> : null}
    </div>
  );
}
