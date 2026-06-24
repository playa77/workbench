/* ==========================================
   Workbench — Tooltip Engine
   Hover-based tooltips with help-page links
   Version: 1.1.0 | 2026-06-24
   ========================================== */

const Tooltips = (() => {
  var currentBubble = null;
  var currentTrigger = null;
  var hideTimer = null;
  var BUBBLE_HIDE_DELAY = 200;
  var ARROW_SIZE = 6;
  var MARGIN = 8;

  function init(container) {
    container = container || document;
    var elements = container.querySelectorAll('[data-tooltip]');
    for (var i = 0; i < elements.length; i++) {
      attach(elements[i]);
    }
  }

  function attach(el) {
    if (el._tooltipAttached) return;
    el._tooltipAttached = true;
    el.addEventListener('mouseenter', onTriggerEnter);
    el.addEventListener('mouseleave', onTriggerLeave);
    el.addEventListener('focus', onTriggerEnter);
    el.addEventListener('blur', onTriggerLeave);
    el.addEventListener('keydown', onTriggerKeydown);
  }

  function onTriggerEnter(e) {
    clearHideTimer();
    if (currentBubble && currentTrigger === e.currentTarget) return;
    destroyBubble();
    showBubble(e.currentTarget);
  }

  function onTriggerLeave() {
    scheduleHide();
  }

  function onTriggerKeydown(e) {
    if (e.key === '?' || e.key === 'F1') {
      e.preventDefault();
      var helpPage = e.currentTarget.dataset.helpPage;
      if (helpPage) {
        window.open(helpPage, '_blank');
      }
    }
  }

  function showBubble(trigger) {
    var text = trigger.dataset.tooltip;
    var helpPage = trigger.dataset.helpPage;
    if (!text && !helpPage) return;

    currentTrigger = trigger;

    var bubble = document.createElement('div');
    bubble.className = 'tooltip-bubble';
    bubble.addEventListener('mouseenter', onBubbleEnter);
    bubble.addEventListener('mouseleave', onBubbleLeave);

    var content = document.createElement('div');
    content.className = 'tooltip-content';

    if (text) {
      var textSpan = document.createElement('span');
      textSpan.className = 'tooltip-text';
      textSpan.textContent = text;
      content.appendChild(textSpan);
    }

    if (helpPage) {
      var helpLink = document.createElement('button');
      helpLink.className = 'tooltip-help-link';
      helpLink.setAttribute('aria-label', 'Open help page');
      helpLink.addEventListener('click', function (ev) {
        ev.stopPropagation();
        ev.preventDefault();
        window.open(helpPage, '_blank');
      });
      content.appendChild(helpLink);
    }

    bubble.appendChild(content);

    var shortcutHint = document.createElement('span');
    shortcutHint.className = 'tooltip-shortcut-hint';
    shortcutHint.textContent = helpPage ? 'Press ? for help' : 'Press ? for shortcut';
    bubble.appendChild(shortcutHint);

    /* Arrow element */
    var arrow = document.createElement('div');
    arrow.className = 'tooltip-bubble-arrow';
    bubble.appendChild(arrow);

    document.body.appendChild(bubble);

    /* Determine placement and position */
    var rect = trigger.getBoundingClientRect();
    var viewportW = window.innerWidth;
    var viewportH = window.innerHeight;

    /* Default: above the element */
    var placement = 'top';
    var bubbleH = bubble.offsetHeight || 60;
    var bubbleW = bubble.offsetWidth || 200;

    var top = rect.top - bubbleH - ARROW_SIZE;
    var left = rect.left + (rect.width / 2) - (bubbleW / 2);

    /* If not enough space above, place below */
    if (top < MARGIN) {
      placement = 'bottom';
      top = rect.bottom + ARROW_SIZE;
    }

    /* Clamp horizontally */
    if (left < MARGIN) {
      left = MARGIN;
    } else if (left + bubbleW > viewportW - MARGIN) {
      left = viewportW - bubbleW - MARGIN;
    }

    bubble.dataset.placement = placement;
    bubble.style.top = top + 'px';
    bubble.style.left = left + 'px';

    currentBubble = bubble;

    /* Trigger reflow then add visible class for transition */
    bubble.offsetHeight;
    bubble.classList.add('visible');
  }

  function destroyBubble() {
    if (currentBubble) {
      if (currentBubble.parentNode) {
        currentBubble.parentNode.removeChild(currentBubble);
      }
      currentBubble = null;
      currentTrigger = null;
    }
  }

  function scheduleHide() {
    hideTimer = setTimeout(function () {
      destroyBubble();
    }, BUBBLE_HIDE_DELAY);
  }

  function clearHideTimer() {
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
  }

  function onBubbleEnter() {
    clearHideTimer();
  }

  function onBubbleLeave() {
    scheduleHide();
  }

  /* MutationObserver: watch for dynamically-added [data-tooltip] elements.
     Tab panels are rendered after the initial DOMContentLoaded, so static
     init misses their inner content. This observer automatically attaches
     tooltip listeners to any new [data-tooltip] nodes inserted into the DOM
     (e.g. after innerHTML assignment in tab render functions).
     Lives inside the IIFE to access the private attach() function. */
  if (typeof MutationObserver !== 'undefined') {
    var tooltipObserver = new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i++) {
        var addedNodes = mutations[i].addedNodes;
        for (var j = 0; j < addedNodes.length; j++) {
          var node = addedNodes[j];
          if (node.nodeType !== 1) continue;
          if (node.hasAttribute && node.hasAttribute('data-tooltip')) {
            attach(node);
          }
          if (node.querySelectorAll) {
            var children = node.querySelectorAll('[data-tooltip]');
            for (var k = 0; k < children.length; k++) {
              attach(children[k]);
            }
          }
        }
      }
    });

    function startTooltipObserver() {
      if (document.body) {
        tooltipObserver.observe(document.body, { childList: true, subtree: true });
      } else {
        setTimeout(startTooltipObserver, 50);
      }
    }
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', startTooltipObserver);
    } else {
      startTooltipObserver();
    }
  }

  return {
    init: init,
  };
})();

/* Auto-initialize on DOM ready for static elements.
   If the DOM is already ready when this script runs,
   initialize immediately. Otherwise wait for the event. */
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function () {
    Tooltips.init();
  });
} else {
  Tooltips.init();
}
