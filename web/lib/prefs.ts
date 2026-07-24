'use client';

/**
 * 로그인 없는 개인화.
 *
 * 브라우저 localStorage 에만 저장하고 서버로 보내지 않는다.
 * 학생 입장에서 가입 절차가 없고, 서비스 입장에서 보관할 개인정보가 없다.
 */

const KEY_BUILDING = 'songsim.building';

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    // 사파리 프라이빗 모드 등에서 접근이 막히면 개인화만 포기한다.
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // 저장에 실패해도 화면 동작에는 영향이 없어야 한다.
  }
}

/** 마지막으로 본 건물 slug. 빈 강의실 화면의 기본값으로 쓴다. */
export function getPreferredBuilding(): string | null {
  return read(KEY_BUILDING);
}

export function setPreferredBuilding(slug: string): void {
  write(KEY_BUILDING, slug);
}
