import { useState } from 'react';
import './mm.css';

/*
 * An image from another site (a post thumbnail, an account photo). Platforms often refuse to serve
 * these to other sites, and a torn-image icon reads worse than no image, so a failed load shows
 * the fallback (or nothing). No referrer is sent, as on the old page.
 */
export function RemoteImage({ src, size = 80, round = false, fallback = null, alt = '' }: {
  src?: string | null;
  size?: number;
  round?: boolean;
  fallback?: React.ReactNode;
  alt?: string;
}) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) return <>{fallback}</>;
  return (
    <img
      className={`mm-remote-img${round ? ' mm-remote-img--round' : ''}`}
      src={src}
      alt={alt}
      width={size}
      height={size}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  );
}

/** An account's photo, round, with a person icon when there is none or it won't load (as the old page) */
export function AccountPhoto({ src, size = 32, icon }: { src?: string | null; size?: number; icon: React.ReactNode }) {
  const fallback = (
    <span className="mm-avatar-fallback" style={{ width: size, height: size }} aria-hidden="true">
      {icon}
    </span>
  );
  return <RemoteImage src={src} size={size} round fallback={fallback} />;
}
