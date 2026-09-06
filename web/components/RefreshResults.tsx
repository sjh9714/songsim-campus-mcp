'use client';

import { useTransition } from 'react';
import { useRouter } from 'next/navigation';

export default function RefreshResults() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return <button type="button" className="chip" disabled={pending}
    onClick={() => startTransition(() => router.refresh())}>
    {pending ? '다시 확인 중…' : '정보 다시 불러오기'}
  </button>;
}
