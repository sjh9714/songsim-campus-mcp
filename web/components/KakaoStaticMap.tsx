'use client';

import Script from 'next/script';
import { useEffect, useRef, useState } from 'react';

type KakaoLatLng = object;

interface KakaoMapsApi {
  load: (callback: () => void) => void;
  LatLng: new (latitude: number, longitude: number) => KakaoLatLng;
  StaticMap: new (
    container: HTMLElement,
    options: {
      center: KakaoLatLng;
      level: number;
      marker: { position: KakaoLatLng; text: string };
    },
  ) => object;
}

declare global {
  interface Window {
    kakao?: { maps: KakaoMapsApi };
  }
}

type MapState = 'loading' | 'ready' | 'missing' | 'error';

const APP_KEY = process.env.NEXT_PUBLIC_KAKAO_MAP_JS_KEY?.trim();

/**
 * 한 장소만 보여주는 이미지 지도.
 *
 * 상세 화면에서 확대·드래그를 받으면 모바일 세로 스크롤을 가로채기 쉽다. 이 화면은
 * 위치 맥락만 빠르게 보여 주고, 실제 탐색은 아래의 Kakao 지도 링크로 넘긴다.
 */
export default function KakaoStaticMap({
  latitude,
  longitude,
  label,
}: {
  latitude: number;
  longitude: number;
  label: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [sdkReady, setSdkReady] = useState(false);
  const [state, setState] = useState<MapState>(APP_KEY ? 'loading' : 'missing');

  useEffect(() => {
    if (state !== 'loading') return;

    const timeout = window.setTimeout(() => setState('error'), 8000);
    return () => window.clearTimeout(timeout);
  }, [sdkReady, state]);

  useEffect(() => {
    if (!sdkReady) return;

    const kakaoMaps = window.kakao?.maps;
    if (!kakaoMaps) {
      setState('error');
      return;
    }

    let disposed = false;
    kakaoMaps.load(() => {
      if (disposed || !containerRef.current) return;

      try {
        const position = new kakaoMaps.LatLng(latitude, longitude);
        containerRef.current.replaceChildren();
        new kakaoMaps.StaticMap(containerRef.current, {
          center: position,
          level: 3,
          marker: { position, text: label },
        });
        setState('ready');
      } catch {
        setState('error');
      }
    });

    return () => {
      disposed = true;
    };
  }, [label, latitude, longitude, sdkReady]);

  const failed = state === 'missing' || state === 'error';

  return (
    <div className="place-map" aria-busy={state === 'loading'}>
      {APP_KEY ? (
        <Script
          id="kakao-static-map-sdk"
          src={`https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(APP_KEY)}&autoload=false`}
          strategy="afterInteractive"
          onReady={() => setSdkReady(true)}
          onError={() => setState('error')}
        />
      ) : null}
      <div
        ref={containerRef}
        className="place-map__canvas"
        role="img"
        aria-label={`${label} 주변 지도`}
      />
      {state !== 'ready' ? (
        <div className={`place-map__state${failed ? ' place-map__state--failed' : ''}`}>
          {failed
            ? '미니 지도를 불러오지 못했어요. 아래 카카오맵 링크로 위치를 확인해 주세요.'
            : '주변 지도를 불러오는 중이에요.'}
        </div>
      ) : null}
    </div>
  );
}
