// src/songsim_campus/schemas.py 를 그대로 미러한 타입.
// 백엔드 스키마를 바꾸면 여기도 같이 바꿔야 한다.

export interface MatchedFacility {
  name: string;
  category: string | null;
  phone: string | null;
  location_hint: string | null;
  opening_hours: string | null;
}

export interface Place {
  id: number;
  slug: string;
  name: string;
  canonical_name: string | null;
  category: string;
  aliases: string[];
  description: string;
  latitude: number | null;
  longitude: number | null;
  opening_hours: Record<string, string>;
  matched_facility: MatchedFacility | null;
  source_tag: string;
  last_synced_at: string;
}

export interface Course {
  id: number;
  year: number;
  semester: number;
  code: string;
  title: string;
  professor: string | null;
  department: string | null;
  section: string | null;
  day_of_week: string | null;
  period_start: number | null;
  period_end: number | null;
  room: string | null;
  raw_schedule: string | null;
  source_tag: string;
  last_synced_at: string;
}

export interface Notice {
  id: number;
  title: string;
  category: string;
  published_at: string;
  summary: string;
  labels: string[];
  source_url: string | null;
  source_tag: string;
  last_synced_at: string;
}

export interface AffiliatedNotice {
  id: number;
  topic: string;
  title: string;
  published_at: string;
  summary: string;
  source_url: string | null;
  source_tag: string;
  last_synced_at: string;
}

export interface NoticeCategoryInfo {
  category: string;
  category_display: string;
  aliases: string[];
}

export interface PhoneBookEntry {
  id: number;
  department: string;
  tasks: string;
  phone: string;
  source_url: string | null;
  source_tag: string;
  last_synced_at: string;
}

export interface PCSoftwareEntry {
  id: number;
  room: string;
  pc_count: number | null;
  software_list: string[];
  source_url: string | null;
  source_tag: string;
  last_synced_at: string;
}

export interface CampusDiningMenu {
  venue_slug: string;
  venue_name: string;
  place_slug: string | null;
  place_name: string | null;
  week_label: string | null;
  week_start: string | null;
  week_end: string | null;
  menu_text: string | null;
  source_url: string | null;
  source_tag: string;
  last_synced_at: string;
}

export interface LibrarySeatStatus {
  room_name: string;
  remaining_seats: number | null;
  occupied_seats: number | null;
  total_seats: number | null;
}

export interface LibrarySeatStatusResponse {
  availability_mode: 'live' | 'stale_cache' | 'unavailable';
  checked_at: string;
  note: string | null;
  source_url: string | null;
  rooms: LibrarySeatStatus[];
}

export interface EmptyClassroomBuilding {
  slug: string;
  name: string;
  canonical_name: string;
  category: string;
  aliases: string[];
}

export interface EstimatedEmptyClassroom {
  room: string;
  available_now: boolean;
  availability_mode: 'realtime' | 'estimated';
  source_observed_at: string | null;
  next_occupied_at: string | null;
  next_course_summary: string | null;
}

export interface EstimatedEmptyClassroomResponse {
  building: EmptyClassroomBuilding;
  evaluated_at: string;
  year: number;
  semester: number;
  availability_mode: 'realtime' | 'estimated' | 'mixed';
  observed_at: string | null;
  estimate_note: string;
  items: EstimatedEmptyClassroom[];
}
