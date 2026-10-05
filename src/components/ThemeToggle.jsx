import { Sun, Moon } from 'lucide-react';
import { useApp } from '../context/AppContext';

export default function ThemeToggle({ className = '' }) {
  const { theme, toggleTheme } = useApp();
  const dark = theme === 'dark';
  return (
    <button
      onClick={toggleTheme}
      title={dark ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro'}
      aria-label={dark ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro'}
      className={`p-2 rounded-lg text-navy-200 hover:bg-white/10 hover:text-white cursor-pointer transition-colors ${className}`}
    >
      {dark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
    </button>
  );
}
