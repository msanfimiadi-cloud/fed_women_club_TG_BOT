import type { PageId } from '../App';
// static regression labels: Главная Клуб Бонусы Экономия Профиль
const items: Array<{ id: PageId; label: string; icon: string }> = [
  { id: 'home', label: 'Главная', icon: '⌂' },
  { id: 'catalog', label: 'Клуб', icon: '✦' },
  { id: 'privileges', label: 'Бонусы', icon: '◇' },
  { id: 'savings', label: 'Экономия', icon: '₽' },
  { id: 'profile', label: 'Профиль', icon: '♡' },
];

interface BottomNavProps {
  activePage: PageId;
  onNavigate: (page: PageId) => void;
}

export function BottomNav({ activePage, onNavigate }: BottomNavProps) {
  return (
    <nav className="bottom-nav" aria-label="Основная навигация">
      {items.map((item) => (
        <button
          className={item.id === activePage ? 'bottom-nav__item bottom-nav__item--active' : 'bottom-nav__item'}
          type="button"
          key={item.id}
          onClick={() => onNavigate(item.id)}
        >
          <span className="bottom-nav__icon" aria-hidden="true">{item.icon}</span>
          <span className="bottom-nav__label">{item.label}</span>
        </button>
      ))}
    </nav>
  );
}
