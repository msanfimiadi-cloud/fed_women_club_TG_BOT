interface EmptyStateProps {
  title: string;
  description: string;
  eyebrow?: string;
  icon?: string;
  actionLabel?: string;
  onAction?: () => void;
  details?: Record<string, string | number | undefined>;
}

export function EmptyState({ title, description, eyebrow = "Пока пусто", icon = "✦", actionLabel, onAction, details }: EmptyStateProps) {
  const visibleDetails = details
    ? Object.entries(details).filter((entry): entry is [string, string | number] => entry[1] !== undefined)
    : [];
  return (
    <div className="state state--empty">
      <span className="state__icon" aria-hidden="true">{icon}</span>
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      <p>{description}</p>
      {visibleDetails.length ? (
        <details className="state__details">
          <summary>Диагностика</summary>
          <dl>
            {visibleDetails.map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{String(value)}</dd>
              </div>
            ))}
          </dl>
        </details>
      ) : null}
      {actionLabel && onAction ? (
        <button className="button button--primary" type="button" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}
