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
    if (!APP_KEY || sdkReady) return;

    const timeout = window.setTimeout(() => setState('error'), 8000);
    return () => window.clearTimeout(timeout);
  }, [sdkReady]);

  useEffect(() => {
    if (!sdkReady) return;

    const kakaoMaps = window.kakao?.maps;
    if (!kakaoMaps) {
      setState('error');
      return;
    }

    const container = containerRef.current;
    if (!container) return;

    let disposed = false;
    let lastSize = '';
    let imageTimeout: number | undefined;
    let resizeTimeout: number | undefined;
    const finish = (next: 'ready' | 'error') => {
      if (disposed) return;
      window.clearTimeout(imageTimeout);
      setState(next);
    };
    const checkImages = () => {
      const images = Array.from(container.querySelectorAll('img'));
      if (images.length > 0 && images.every((image) => image.complete && image.naturalWidth > 0)) finish('ready');
    };
    const imageError = () => finish('error');
    const imageObserver = new MutationObserver(checkImages);
    imageObserver.observe(container, { childList: true, subtree: true });
    container.addEventListener('load', checkImages, true);
    container.addEventListener('error', imageError, true);

    const draw = () => {
      if (disposed || !container.clientWidth || !container.clientHeight) return;
      const size = `${container.clientWidth}x${container.clientHeight}`;
      if (size === lastSize) return;
      lastSize = size;
      setState('loading');
      window.clearTimeout(imageTimeout);
      imageTimeout = window.setTimeout(() => finish('error'), 8000);

      try {
        const position = new kakaoMaps.LatLng(latitude, longitude);
        // StaticMap has no documented relayout API. Recreate the image at its actual
        // container size instead of stretching an old image after mobile rotation.
        container.replaceChildren();
        new kakaoMaps.StaticMap(container, {
          center: position,
          level: 3,
          marker: { position, text: label },
        });
        checkImages();
      } catch {
        finish('error');
      }
    };
    const resizeObserver = new ResizeObserver(() => {
      window.clearTimeout(resizeTimeout);
      resizeTimeout = window.setTimeout(draw, 120);
    });
    imageTimeout = window.setTimeout(() => finish('error'), 8000);
    try {
      kakaoMaps.load(() => {
        if (disposed) return;
        draw();
        resizeObserver.observe(container);
      });
    } catch {
      finish('error');
    }

    return () => {
      disposed = true;
      window.clearTimeout(imageTimeout);
      window.clearTimeout(resizeTimeout);
      resizeObserver.disconnect();
      imageObserver.disconnect();
      container.removeEventListener('load', checkImages, true);
      container.removeEventListener('error', imageError, true);
      container.replaceChildren();
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
