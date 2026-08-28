import { placeBuildingCode, placeCanonicalName } from '@/lib/places';
import type { Place } from '@/lib/types';

export default function PlaceIdentity({
  place,
  className = 'row__title',
}: {
  place: Place;
  className?: string;
}) {
  const code = placeBuildingCode(place);

  return (
    <span className={className}>
      {placeCanonicalName(place)}
      {code ? <span className="place-code">{code}</span> : null}
    </span>
  );
}
