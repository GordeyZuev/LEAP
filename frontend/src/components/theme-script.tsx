/**
 * Inline, render-blocking script that sets the `dark` class on <html> before
 * first paint, preventing a flash of the wrong theme (FOUC). Reads the same
 * localStorage key and media query as the runtime theme hook.
 */
export function ThemeScript() {
  const js = `(function(){try{var t=localStorage.getItem('theme')||'system';var m=window.matchMedia('(prefers-color-scheme: dark)').matches;var d=t==='dark'||(t==='system'&&m);document.documentElement.classList.toggle('dark',d);}catch(e){}})();`;
  return <script dangerouslySetInnerHTML={{ __html: js }} />;
}
