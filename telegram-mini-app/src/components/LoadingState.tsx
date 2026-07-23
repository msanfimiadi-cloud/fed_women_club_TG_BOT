interface LoadingStateProps {
  title?: string;
  compact?: boolean;
}

export function LoadingState({ title = 'Загружаем данные клуба', compact = false }: LoadingStateProps) {
  return (
    <div className={compact ? 'state state--loading state--compact' : 'state state--loading'} role="status">
      <span className="spinner" aria-hidden="true" />
      <p>{title}</p>
    </div>
  );
}
