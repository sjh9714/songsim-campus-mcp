'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

import { getPreferredBuilding, setPreferredBuilding } from '@/lib/prefs';

/**
 * 빈 강의실을 볼 건물 선택.
 *
 * 주소에 building 이 없으면 지난번에 봤던 건물로 한 번 되돌린다.
 * 매번 같은 건물을 다시 고르게 하지 않으려는 것뿐이라, 실패하면 그냥 기본값으로 둔다.
 */
export default function BuildingPicker({
  buildings,
  selected,
  hasExplicitSelection,
}: {
  buildings: { slug: string; name: string }[];
  selected: string | undefined;
  hasExplicitSelection: boolean;
}) {
  const router = useRouter();
  const slugs = buildings.map((building) => building.slug).join(',');

  useEffect(() => {
    if (hasExplicitSelection) return;
    const preferred = getPreferredBuilding();
    if (!preferred || preferred === selected) return;
    if (!slugs.split(',').includes(preferred)) return;
    router.replace(`/study?building=${encodeURIComponent(preferred)}`);
  }, [hasExplicitSelection, slugs, selected, router]);

  return (
    <div className="chips">
      {buildings.map((building) => (
        <button
          key={building.slug}
          type="button"
          className="chip"
          aria-pressed={building.slug === selected}
          onClick={() => {
            setPreferredBuilding(building.slug);
            router.push(`/study?building=${encodeURIComponent(building.slug)}`);
          }}
        >
          {building.name}
        </button>
      ))}
    </div>
  );
}
