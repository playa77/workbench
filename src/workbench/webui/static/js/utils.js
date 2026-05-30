/* ==========================================
   Workbench — Utility Helpers
   ========================================== */

const Utils = (() => {
  const entityMap = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  };

  function escapeHtml(str) {
    if (!str || typeof str !== 'string') return '';
    return str.replace(/[&<>"']/g, function (c) {
      return entityMap[c];
    });
  }

  return { escapeHtml };
})();
