// Inline script that runs before React hydration to set the .dark class on
// <html> based on localStorage. Without this the page would briefly paint in
// the default theme and then flash to the user's preference once JS loaded.
export function ThemeBoot() {
  const code = `
(function(){try{
  var k='gink-theme';
  var v=localStorage.getItem(k);
  var prefersDark=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches;
  var dark = v ? v==='dark' : (prefersDark || v===null);
  if (dark) document.documentElement.classList.add('dark');
  else document.documentElement.classList.remove('dark');
}catch(e){document.documentElement.classList.add('dark');}})();
`;
  return <script dangerouslySetInnerHTML={{ __html: code }} />;
}
