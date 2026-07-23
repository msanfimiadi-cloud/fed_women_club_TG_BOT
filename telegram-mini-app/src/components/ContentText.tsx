import type { ReactNode } from 'react';
import { useContentText } from '../content/ContentContext';

type ContentTextProps = {
  as?: 'span' | 'p' | 'strong' | 'h1' | 'h2' | 'h3' | 'small' | 'em';
  textKey: string;
  fallback: string;
  className?: string;
  multiline?: boolean;
  children?: ReactNode;
};

export function ContentText({
  as = 'span',
  textKey,
  fallback,
  className,
  multiline = false,
}: ContentTextProps) {
  const value = useContentText(textKey, fallback);
  const content = multiline
    ? value.split('\n').map((line, index, lines) => (
        <span key={`${line}-${index}`}>
          {line}
          {index < lines.length - 1 ? <br /> : null}
        </span>
      ))
    : value;

  if (as === 'p') return <p className={className}>{content}</p>;
  if (as === 'strong') return <strong className={className}>{content}</strong>;
  if (as === 'h1') return <h1 className={className}>{content}</h1>;
  if (as === 'h2') return <h2 className={className}>{content}</h2>;
  if (as === 'h3') return <h3 className={className}>{content}</h3>;
  if (as === 'small') return <small className={className}>{content}</small>;
  if (as === 'em') return <em className={className}>{content}</em>;
  return <span className={className}>{content}</span>;
}
