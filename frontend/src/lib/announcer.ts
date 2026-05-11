let announcer: HTMLDivElement | null = null;

function getAnnouncer(): HTMLDivElement {
  if (!announcer) {
    announcer = document.createElement('div');
    announcer.setAttribute('role', 'status');
    announcer.setAttribute('aria-live', 'polite');
    announcer.setAttribute('aria-atomic', 'true');
    announcer.className = 'sr-only';
    document.body.appendChild(announcer);
  }
  return announcer;
}

export function announce(message: string): void {
  const el = getAnnouncer();
  el.textContent = '';
  requestAnimationFrame(() => {
    el.textContent = message;
  });
}
