import './Tile.css';

export interface TileProps {
  /** Machine name, set in Geist Mono, e.g. "search_news" */
  name: string;
  /** Clamped to 3 lines. */
  description?: string;
  className?: string;
}

/** Inset card for a tool or recipe: mono name + short description (clamped to 3 lines). */
export function Tile({ name, description, className }: TileProps) {
  return (
    <div className={['tile', className].filter(Boolean).join(' ')}>
      <div className="tile__name">{name}</div>
      {description && <div className="tile__description">{description}</div>}
    </div>
  );
}
