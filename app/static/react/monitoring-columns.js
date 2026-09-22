const VISIBLE_COLUMNS_STORAGE_KEY = "coramail.monitoring.visibleColumns.v1";
const COLUMN_WIDTHS_STORAGE_KEY = "coramail.monitoring.columnWidths.v1";
const COLUMN_ORDER_STORAGE_KEY = "coramail.monitoring.columnOrder.v1";

function monitoringColumnDefaults() {
  return {
    health: true,
    subject: true,
    sender: true,
    business: true,
    assignee: true,
    received: true,
    attachment: true,
    summary: true,
    classification: true,
    decision: true,
    routing: true,
    forwarding: true,
    control: true,
  };
}

function monitoringColumnWidthDefaults() {
  return {
    health: 64,
    subject: 450,
    sender: 82,
    business: 112,
    assignee: 138,
    received: 116,
    attachment: 150,
    summary: 150,
    classification: 150,
    decision: 184,
    routing: 150,
    forwarding: 150,
  };
}

function monitoringColumnOrderDefaults() {
  return ["health", "subject", "sender", "business", "assignee", "received", "attachment", "summary", "classification", "decision", "routing", "forwarding"];
}

function readMonitoringColumns() {
  const defaults = monitoringColumnDefaults();
  try {
    const raw = window.localStorage?.getItem(VISIBLE_COLUMNS_STORAGE_KEY) || "";
    return { ...defaults, ...(raw ? JSON.parse(raw) : {}) };
  } catch {
    return defaults;
  }
}

function saveMonitoringColumns(columns) {
  try {
    window.localStorage?.setItem(VISIBLE_COLUMNS_STORAGE_KEY, JSON.stringify(columns));
  } catch {
    return;
  }
}

function readMonitoringColumnWidths() {
  const defaults = monitoringColumnWidthDefaults();
  try {
    const raw = window.localStorage?.getItem(COLUMN_WIDTHS_STORAGE_KEY) || "";
    const parsed = raw ? JSON.parse(raw) : {};
    const widths = { ...defaults };
    Object.keys(parsed || {}).forEach((key) => {
      const width = Number(parsed[key]);
      if (Number.isFinite(width)) widths[key] = Math.max(48, Math.min(720, Math.round(width)));
    });
    return widths;
  } catch {
    return defaults;
  }
}

function saveMonitoringColumnWidths(widths) {
  try {
    window.localStorage?.setItem(COLUMN_WIDTHS_STORAGE_KEY, JSON.stringify(widths));
  } catch {
    return;
  }
}

function readMonitoringColumnOrder() {
  const defaults = monitoringColumnOrderDefaults();
  try {
    const raw = window.localStorage?.getItem(COLUMN_ORDER_STORAGE_KEY) || "";
    const parsed = raw ? JSON.parse(raw) : [];
    const known = new Set(defaults);
    const ordered = Array.isArray(parsed) ? parsed.filter((key) => known.has(key) && key !== "health") : [];
    defaults.forEach((key) => {
      if (key !== "health" && !ordered.includes(key)) ordered.push(key);
    });
    return ["health", ...ordered];
  } catch {
    return defaults;
  }
}

function saveMonitoringColumnOrder(order) {
  try {
    window.localStorage?.setItem(COLUMN_ORDER_STORAGE_KEY, JSON.stringify(order));
  } catch {
    return;
  }
}

function applyMonitoringColumnOrder(view) {
  if (!view) return;
  const table = view.querySelector(".ops-table");
  if (!table) return;
  const order = readMonitoringColumnOrder();
  const appendOrdered = (parent, selector) => {
    if (!parent) return;
    order.forEach((key) => {
      const node = parent.querySelector(`${selector}[data-monitoring-column='${CSS.escape(key)}']`);
      if (node) parent.appendChild(node);
    });
  };
  appendOrdered(table.querySelector("colgroup"), "col");
  appendOrdered(table.querySelector("thead tr"), "th");
  table.querySelectorAll("tbody tr").forEach((row) => appendOrdered(row, "td"));
}

function applyMonitoringColumnWidths(view) {
  if (!view) return;
  const table = view.querySelector(".ops-table");
  if (!table) return;
  const visibleColumns = readMonitoringColumns();
  const widths = readMonitoringColumnWidths();
  let visibleWidth = 0;
  table.querySelectorAll("col[data-monitoring-column]").forEach((col) => {
    const key = col.getAttribute("data-monitoring-column") || "";
    const width = widths[key];
    if (width) {
      col.style.width = `${width}px`;
      col.style.minWidth = `${width}px`;
    }
    if (visibleColumns[key] !== false && width) visibleWidth += width;
  });
  if (visibleWidth > 0) {
    const wrap = table.closest(".ops-table-wrap");
    const frameWidth = wrap ? Math.floor(wrap.clientWidth) : 0;
    table.style.width = `${Math.max(visibleWidth, frameWidth)}px`;
    table.style.minWidth = `${visibleWidth}px`;
  }
}

function updateMonitoringTerminalColumn(view) {
  if (!view) return;
  const headers = Array.from(view.querySelectorAll("th[data-monitoring-column]"));
  headers.forEach((header) => header.classList.remove("is-terminal-visible-column"));
  const terminalHeader = headers.filter((header) => !header.hidden).at(-1);
  if (terminalHeader) terminalHeader.classList.add("is-terminal-visible-column");
}

function monitoringColumnWidthBounds(key) {
  return {
    min: key === "subject" ? 180 : key === "health" ? 48 : 72,
    max: key === "subject" ? 720 : 360,
  };
}

function nextVisibleMonitoringColumnKey(header) {
  let next = header?.nextElementSibling || null;
  while (next) {
    if (next.matches?.("th[data-monitoring-column]") && !next.hidden) return next.getAttribute("data-monitoring-column") || "";
    next = next.nextElementSibling;
  }
  return "";
}

function applyMonitoringColumns(root) {
  const scope = root?.querySelector ? root : document;
  const columns = readMonitoringColumns();
  const view = scope.matches?.(".ops-view[data-view='monitoring']") ? scope : scope.querySelector(".ops-view[data-view='monitoring']");
  applyMonitoringColumnOrder(view);
  scope.querySelectorAll("[data-monitoring-column]").forEach((node) => {
    const key = node.getAttribute("data-monitoring-column") || "";
    node.hidden = columns[key] === false;
  });
  scope.querySelectorAll("[data-monitoring-column-toggle]").forEach((input) => {
    const key = input.getAttribute("data-monitoring-column-toggle") || "";
    input.checked = columns[key] !== false;
  });
  applyMonitoringColumnWidths(view);
  updateMonitoringTerminalColumn(view);
}

function initMonitoringColumnResize(view) {
  const table = view?.querySelector(".ops-table");
  if (!table) return;
  view.querySelectorAll("[data-monitoring-column-resizer]").forEach((handle) => {
    if (handle.dataset.monitoringColumnResizeBound) return;
    handle.dataset.monitoringColumnResizeBound = "true";
    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== undefined && event.button !== 0) return;
      const key = handle.getAttribute("data-monitoring-column-resizer") || "";
      const header = handle.closest("th[data-monitoring-column]");
      const col = table.querySelector(`col[data-monitoring-column='${CSS.escape(key)}']`);
      if (header?.classList.contains("is-terminal-visible-column") || !key || !header || !col) return;
      const nextKey = nextVisibleMonitoringColumnKey(header);
      const nextCol = nextKey ? table.querySelector(`col[data-monitoring-column='${CSS.escape(nextKey)}']`) : null;
      if (!nextKey || !nextCol) return;
      event.preventDefault();
      event.stopPropagation();
      const startX = event.clientX;
      const startWidth = col.getBoundingClientRect().width || header.getBoundingClientRect().width;
      const nextStartWidth = nextCol.getBoundingClientRect().width || startWidth;
      const widths = readMonitoringColumnWidths();
      const bounds = monitoringColumnWidthBounds(key);
      const nextBounds = monitoringColumnWidthBounds(nextKey);
      table.classList.add("is-column-resizing");
      header.classList.add("is-resizing");
      try {
        handle.setPointerCapture?.(event.pointerId);
      } catch {
        return;
      }
      const onMove = (moveEvent) => {
        const rawDelta = Math.round(moveEvent.clientX - startX);
        const minDelta = Math.max(bounds.min - startWidth, nextStartWidth - nextBounds.max);
        const maxDelta = Math.min(bounds.max - startWidth, nextStartWidth - nextBounds.min);
        const delta = Math.max(minDelta, Math.min(maxDelta, rawDelta));
        widths[key] = Math.round(startWidth + delta);
        widths[nextKey] = Math.round(nextStartWidth - delta);
        saveMonitoringColumnWidths(widths);
        applyMonitoringColumnWidths(view);
      };
      const onEnd = () => {
        table.classList.remove("is-column-resizing");
        header.classList.remove("is-resizing");
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onEnd);
        window.removeEventListener("pointercancel", onEnd);
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onEnd);
      window.addEventListener("pointercancel", onEnd);
    });
  });
}

function initMonitoringColumnReorder(view) {
  const table = view?.querySelector(".ops-table");
  if (!table) return;
  view.querySelectorAll("th[data-monitoring-column]").forEach((header) => {
    if (header.dataset.monitoringColumnReorderBound) return;
    header.dataset.monitoringColumnReorderBound = "true";
    header.addEventListener("pointerdown", (event) => {
      if (event.button !== undefined && event.button !== 0) return;
      if (event.target?.closest(".ops-column-resizer, button, a, input, select, summary, details, label")) return;
      const key = header.getAttribute("data-monitoring-column") || "";
      if (!key || key === "health") return;
      let longPressTimer = 0;
      let active = false;
      let currentOrder = readMonitoringColumnOrder();
      const startX = event.clientX;
      const startY = event.clientY;
      const clearLongPress = () => {
        if (!longPressTimer) return;
        window.clearTimeout(longPressTimer);
        longPressTimer = 0;
      };
      const activate = () => {
        active = true;
        table.classList.add("is-column-reordering");
        header.classList.add("is-reordering");
      };
      const onMove = (moveEvent) => {
        if (!active) {
          const moved = Math.abs(moveEvent.clientX - startX) + Math.abs(moveEvent.clientY - startY);
          if (moved > 8) clearLongPress();
          return;
        }
        moveEvent.preventDefault();
        const target = document.elementFromPoint(moveEvent.clientX, moveEvent.clientY);
        const targetHeader = target?.closest("th[data-monitoring-column]");
        const targetKey = targetHeader?.getAttribute("data-monitoring-column") || "";
        if (!targetKey || targetKey === "health" || targetKey === key) return;
        const fromIndex = currentOrder.indexOf(key);
        const toIndex = currentOrder.indexOf(targetKey);
        if (fromIndex <= 0 || toIndex <= 0 || fromIndex === toIndex) return;
        currentOrder.splice(fromIndex, 1);
        currentOrder.splice(toIndex, 0, key);
        saveMonitoringColumnOrder(currentOrder);
        applyMonitoringColumns(view);
      };
      const onEnd = () => {
        clearLongPress();
        if (active) {
          table.classList.remove("is-column-reordering");
          view.querySelectorAll("th.is-reordering").forEach((node) => node.classList.remove("is-reordering"));
          saveMonitoringColumnOrder(currentOrder);
        }
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onEnd);
        window.removeEventListener("pointercancel", onEnd);
      };
      try {
        header.setPointerCapture?.(event.pointerId);
      } catch {
        return;
      }
      longPressTimer = window.setTimeout(activate, 320);
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onEnd);
      window.addEventListener("pointercancel", onEnd);
    });
  });
}

export function initMonitoringColumns(root = document) {
  const scope = root?.querySelector ? root : document;
  const view = scope.matches?.(".ops-view[data-view='monitoring']") ? scope : scope.querySelector(".ops-view[data-view='monitoring']");
  if (!view) return;
  applyMonitoringColumns(view);
  initMonitoringColumnResize(view);
  initMonitoringColumnReorder(view);
  view.querySelectorAll("[data-monitoring-column-toggle]").forEach((input) => {
    if (input.dataset.monitoringColumnBound) return;
    input.dataset.monitoringColumnBound = "true";
    input.addEventListener("change", () => {
      const columns = readMonitoringColumns();
      const key = input.getAttribute("data-monitoring-column-toggle") || "";
      columns[key] = input.checked;
      saveMonitoringColumns(columns);
      applyMonitoringColumns(view);
      applyMonitoringColumnWidths(view);
    });
  });
}
