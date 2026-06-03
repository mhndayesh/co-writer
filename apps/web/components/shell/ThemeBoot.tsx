// Inline script — runs before React to set data-mode/data-dir on <html>.
// Prevents flash: page paints with correct palette before JS hydrates.
export function ThemeBoot() {
  const code = `
(function(){
  try {
    var stored = localStorage.getItem('inkwell-theme');
    // Legacy key fallback
    if (!stored) stored = localStorage.getItem('gink-theme') === 'dark' ? 'dark' : null;
    var mode = (stored === 'dark' || stored === 'soft' || stored === 'light') ? stored : 'dark';
    var dir = localStorage.getItem('inkwell-dir') || 'ember';
    var html = document.documentElement;
    html.setAttribute('data-mode', mode);
    html.setAttribute('data-dir', dir);
    if (mode === 'dark') html.classList.add('dark');
    else html.classList.remove('dark');
  } catch(e) {
    document.documentElement.setAttribute('data-mode', 'soft');
    document.documentElement.setAttribute('data-dir', 'ember');
  }
})();
`;
  return <script dangerouslySetInnerHTML={{ __html: code }} />;
}
