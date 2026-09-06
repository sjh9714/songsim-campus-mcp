import { NextRequest, NextResponse } from 'next/server';
import { getEmptyClassrooms, getLibrarySeats } from '@/lib/api';

export const dynamic = 'force-dynamic';
export const maxDuration = 60;

export async function GET(request: NextRequest) {
  const kind = request.nextUrl.searchParams.get('kind');
  const building = request.nextUrl.searchParams.get('building') ?? '';
  let result;
  if (kind === 'library-seats') {
    result = await getLibrarySeats({ fresh: true });
  } else if (kind === 'classrooms' && /^[a-z0-9-]{1,80}$/.test(building)) {
    result = await getEmptyClassrooms(building, 10, { fresh: true });
  } else {
    return NextResponse.json({ error: 'Invalid live request' }, { status: 400 });
  }
  return NextResponse.json(result, { headers: { 'Cache-Control': 'no-store' } });
}
