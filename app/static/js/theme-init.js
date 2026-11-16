// Laeuft vor dem Zeichnen der Seite, damit Hell/Dunkel nicht aufblitzt.
try {
  const t = localStorage.getItem('hz-theme');
  if (t === 'dark' || t === 'light') document.documentElement.dataset.theme = t;
} catch (e) { /* ohne Speicher: Systemeinstellung */ }
