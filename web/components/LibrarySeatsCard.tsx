import { getLibrarySeats } from '@/lib/api';
import LibrarySeatsView from './LibrarySeatsView';

export default async function LibrarySeatsCard({ compact = false }: { compact?: boolean }) {
  return <LibrarySeatsView initial={await getLibrarySeats()} compact={compact} />;
}
