// Simple line icon set — 24x24, stroke 2, currentColor는 CSS(.row svg)에서 #2563EB 로 고정.
// 페이지마다 아이콘 스타일을 바꾸지 않는다. 필요한 키만 여기서 늘린다.
const P = d => `<svg viewBox="0 0 24 24">${d}</svg>`;
var ICON = {
  dot:      P('<circle cx="12" cy="12" r="7"/>'),
  search:   P('<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.3-4.3"/>'),
  list:     P('<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>'),
  plus:     P('<circle cx="12" cy="12" r="8"/><path d="M12 8.5v7M8.5 12h7"/>'),
  filter:   P('<path d="M4 5h16l-6.3 7.4V19l-3.4 2v-8.6z"/>'),
  settings: P('<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>'),
  download: P('<path d="M12 4v10m0 0l-3.5-3.5M12 14l3.5-3.5M4 18v2h16v-2"/>'),
  upload:   P('<path d="M12 20V10m0 0L8.5 13.5M12 10l3.5 3.5M4 6V4h16v2"/>'),
  calendar: P('<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>'),
  clock:    P('<circle cx="12" cy="12" r="8"/><path d="M12 8v4.5l3 1.8"/>'),
  user:     P('<circle cx="12" cy="8.5" r="3.5"/><path d="M5 20c0-3.6 3.1-5.5 7-5.5s7 1.9 7 5.5"/>'),
  users:    P('<circle cx="9" cy="8.5" r="3"/><path d="M3 19c0-3.2 2.7-4.8 6-4.8s6 1.6 6 4.8"/><path d="M17 7.2a3 3 0 010 5.6M18 19c0-2.2-.6-3.6-1.6-4.5"/>'),
  building: P('<path d="M4 20V6l7-3v17M11 20h9V10l-9-3"/><path d="M14.5 12h2M14.5 15.5h2"/>'),
  chart:    P('<path d="M4 20V4"/><path d="M4 20h16"/><path d="M8 17v-5M12.5 17V8M17 17v-7"/>'),
  doc:      P('<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>'),
  edit:     P('<path d="M5 19h14"/><path d="M15.5 4.5l3 3L9 17l-4 1 1-4z"/>'),
  check:    P('<circle cx="12" cy="12" r="8"/><path d="M8.5 12.2l2.4 2.4 4.6-4.9"/>'),
  bell:     P('<path d="M6 16V11a6 6 0 1112 0v5l2 2H4z"/><path d="M10 21h4"/>'),
  send:     P('<path d="M20.5 3.5L11 13"/><path d="M20.5 3.5L14 20.5l-3-7.5-7.5-3z"/>'),
  link:     P('<path d="M10.5 13.5a4 4 0 005.7 0l2.3-2.3a4 4 0 10-5.7-5.7L11.6 6.7"/><path d="M13.5 10.5a4 4 0 00-5.7 0l-2.3 2.3a4 4 0 105.7 5.7l1.2-1.2"/>'),
  sparkle:  P('<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M18.5 16.5l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"/>'),
  money:    P('<circle cx="12" cy="12" r="8"/><path d="M14.5 9.3c-.6-.7-1.5-1-2.5-1-1.4 0-2.5.7-2.5 1.8 0 2.4 5 1 5 3.5 0 1.1-1.1 1.9-2.5 1.9-1.1 0-2-.4-2.6-1.1M12 6.8v10.4"/>'),
  mic:      P('<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0013 0M12 18v3"/>'),
  folder:   P('<path d="M3 7a2 2 0 012-2h4l2 2.5h8a2 2 0 012 2V17a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>'),
};
