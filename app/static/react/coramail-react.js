import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Chart, registerables } from "chart.js";

const h = React.createElement;
Chart.register(...registerables);
window.Chart = Chart;

const VIEW_ENDPOINTS = {
  dashboard: "/ui/dashboard",
  inbox: "/ui/inbox",
  monitoring: "/ui/monitoring",
  assignees: "/ui/assignees",
  "my-work": "/ui/my-work",
  documents: "/ui/documents",
  "address-book": "/ui/address-book",
  search: "/ui/search",
  chats: "/ui/chats",
  settings: "/ui/settings",
};

const VIEW_TITLES = {
  dashboard: "Dashboard",
  inbox: "Inbox",
  monitoring: "Monitoring",
  assignees: "Assignments",
  "my-work": "My Work",
  documents: "Documents",
  "address-book": "Contacts",
  search: "Search",
  chats: "Chats",
  settings: "Settings",
};

const VIEW_ICONS = {
  dashboard: "dashboard",
  inbox: "inbox",
  monitoring: "monitoring",
  assignees: "assignment_ind",
  "my-work": "assignment_ind",
  documents: "description",
  "address-book": "contacts",
  search: "search",
  chats: "forum",
  settings: "settings",
};

function initialState() {
  const node = document.getElementById("coramail-react-state");
  if (!node?.textContent) return { activeView: "dashboard" };
  try {
    return JSON.parse(node.textContent);
  } catch {
    return { activeView: "dashboard" };
  }
}

function initialViewHtml() {
  const template = document.getElementById("coramail-react-initial-view");
  return template?.innerHTML || "";
}

function navItems(state) {
  const workView = state.currentUserCanViewAllAssignees ? "assignees" : "my-work";
  return [
    "dashboard",
    "inbox",
    "monitoring",
    workView,
    ...(state.demoMode ? [] : ["documents"]),
    "address-book",
    "search",
    "chats",
    "settings",
  ];
}

function requestHeaders() {
  return {
    "X-Requested-With": "XMLHttpRequest",
    "HX-Request": "true",
    Accept: "text/html",
  };
}

function formBody(form, extraPairs = []) {
  const params = new URLSearchParams();
  if (form) {
    const data = new FormData(form);
    for (const [key, value] of data.entries()) params.set(key, value);
  }
  for (const [key, value] of extraPairs) params.set(key, value);
  return params;
}

function parseHxVals(element) {
  const raw = element?.getAttribute("hx-vals");
  if (!raw) return [];
  try {
    return Object.entries(JSON.parse(raw));
  } catch {
    return [];
  }
}

function includedPairs(element) {
  const selectors = String(element?.getAttribute("hx-include") || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const pairs = [];
  for (const selector of selectors) {
    document.querySelectorAll(selector).forEach((node) => {
      if (!node.name) return;
      pairs.push([node.name, node.value || ""]);
    });
  }
  return pairs;
}

function targetFor(element) {
  const selector = element?.getAttribute("hx-target") || element?.closest("[hx-target]")?.getAttribute("hx-target");
  if (!selector) return element;
  if (selector.startsWith("closest ")) return element.closest(selector.slice("closest ".length));
  return document.querySelector(selector);
}

function swapTarget(target, html, swap) {
  if (!target || swap === "none") return;
  const template = document.createElement("template");
  template.innerHTML = html;
  template.content.querySelectorAll("[hx-swap-oob='true']").forEach((node) => {
    if (node.id) {
      const existing = document.getElementById(node.id);
      if (existing) existing.replaceWith(node);
    }
    node.remove();
  });
  if (swap === "outerHTML") {
    target.outerHTML = template.innerHTML;
    window.requestAnimationFrame(() => {
      hydrateFavoriteMailButtons(document);
      initializeProgressToggles(document);
      updateSlidingTabs(document, true);
      initDashboardCharts(document);
    });
    return;
  }
  target.innerHTML = template.innerHTML;
  window.requestAnimationFrame(() => {
    hydrateFavoriteMailButtons(target);
    initializeProgressToggles(target);
    updateSlidingTabs(target, true);
    initDashboardCharts(target);
  });
}

function viewForUrl(url) {
  const parsed = new URL(url, window.location.origin);
  return (
    Object.entries(VIEW_ENDPOINTS).find(([, path]) => path === parsed.pathname)?.[0] ||
    parsed.searchParams.get("view") ||
    ""
  );
}

function dispatchHxTriggers(response) {
  const raw = response.headers.get("HX-Trigger");
  if (!raw) return;
  try {
    const parsed = JSON.parse(raw);
    Object.entries(parsed).forEach(([name, detail]) => document.body.dispatchEvent(new CustomEvent(name, { detail })));
  } catch {
    raw.split(",").map((name) => name.trim()).filter(Boolean).forEach((name) => {
      document.body.dispatchEvent(new CustomEvent(name));
    });
  }
}

function loadTriggerElements(root = document) {
  return Array.from(root.querySelectorAll("[hx-trigger~='load'][hx-get], [hx-trigger~='load'][hx-post]"));
}

const FAVORITE_MAIL_STORAGE_KEY = "coramail.favoriteMailUids.v1";

function readFavoriteMailUids() {
  try {
    const raw = window.localStorage?.getItem(FAVORITE_MAIL_STORAGE_KEY) || "";
    const parsed = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed.map(String).filter(Boolean) : []);
  } catch {
    return new Set();
  }
}

function writeFavoriteMailUids(values) {
  try {
    window.localStorage?.setItem(FAVORITE_MAIL_STORAGE_KEY, JSON.stringify(Array.from(values)));
  } catch {
    return;
  }
}

function setFavoriteButtonState(button, liked) {
  button.dataset.liked = liked ? "true" : "false";
  button.setAttribute("aria-pressed", liked ? "true" : "false");
  button.setAttribute("aria-label", liked ? "즐겨찾기 제거" : "즐겨찾기 추가");
  button.setAttribute("title", liked ? "즐겨찾기 제거" : "즐겨찾기 추가");
  button.closest("[data-email-uid]")?.classList.toggle("is-mail-favorite", liked);
}

function seedLikeParticles(button) {
  const dots = button.querySelectorAll(".t-like-particles i");
  dots.forEach((dot, index) => {
    const angle = (360 / dots.length) * index + (Math.random() * 2 - 1) * 16;
    const mag = 20 * (0.68 + Math.random() * 0.5);
    const rad = (angle * Math.PI) / 180;
    const style = dot.style;
    style.setProperty("--px", `${(Math.cos(rad) * mag).toFixed(2)}px`);
    style.setProperty("--py", `${(Math.sin(rad) * mag).toFixed(2)}px`);
    style.setProperty("--pdur", `calc(var(--like-particle-dur) * ${(0.78 + Math.random() * 0.44).toFixed(3)})`);
    style.setProperty("--pdelay", `${Math.round(Math.random() * 70)}ms`);
    style.setProperty("--p-end-scale", (0.35 + Math.random() * 0.4).toFixed(2));
    style.setProperty("--psize", (0.6 + Math.random() * 0.8).toFixed(2));
  });
}

function replayMailRowClickTransition(row) {
  if (!row) return;
  row.classList.remove("is-click-transition");
  void row.offsetWidth;
  row.classList.add("is-click-transition");
  window.setTimeout(() => {
    row.classList.remove("is-click-transition");
  }, 320);
}

function hydrateFavoriteMailButtons(root = document) {
  const favorites = readFavoriteMailUids();
  root.querySelectorAll?.("[data-mail-favorite-toggle][data-email-uid]").forEach((button) => {
    setFavoriteButtonState(button, favorites.has(String(button.dataset.emailUid || "")));
  });
}

function toggleFavoriteMail(button) {
  const emailUid = String(button.dataset.emailUid || "");
  if (!emailUid) return;
  replayMailRowClickTransition(button.closest("#mailRows .clickable-row[data-email-uid], #dashboardMailRows .clickable-row[data-email-uid]"));
  const favorites = readFavoriteMailUids();
  const liked = !favorites.has(emailUid);
  if (liked) favorites.add(emailUid);
  else favorites.delete(emailUid);
  writeFavoriteMailUids(favorites);
  document.querySelectorAll(`[data-mail-favorite-toggle][data-email-uid="${CSS.escape(emailUid)}"]`).forEach((item) => {
    item.classList.remove("is-bursting");
    setFavoriteButtonState(item, liked);
  });
  if (liked) {
    seedLikeParticles(button);
    void button.offsetWidth;
    button.classList.add("is-bursting");
  }
}

function handleFavoriteMailClick(event) {
  const favoriteButton = event.target?.closest?.("[data-mail-favorite-toggle]");
  if (!favoriteButton) return;
  event.preventDefault();
  event.stopPropagation();
  toggleFavoriteMail(favoriteButton);
}

function initializeProgressToggles(root = document) {
  root.querySelectorAll?.("[data-work-in-progress-toggle].t-toggle").forEach((button) => {
    button.classList.remove("is-init");
  });
}

function MaterialIcon({ children }) {
  return h("span", { className: "material-symbols-outlined", "aria-hidden": "true" }, children);
}

function updateSlidingTabGroup(group, activeButton, snap = false) {
  if (!(group instanceof HTMLElement) || !(activeButton instanceof HTMLElement)) return;
  if (snap) group.classList.add("is-sliding-tabs-snapping");
  const groupRect = group.getBoundingClientRect();
  const buttonRect = activeButton.getBoundingClientRect();
  const x = buttonRect.left - groupRect.left;
  const y = buttonRect.top - groupRect.top;
  group.style.setProperty("--sliding-tab-x", `${Math.round(x)}px`);
  group.style.setProperty("--sliding-tab-y", `${Math.round(y)}px`);
  group.style.setProperty("--sliding-tab-width", `${Math.round(buttonRect.width)}px`);
  group.style.setProperty("--sliding-tab-height", `${Math.round(buttonRect.height)}px`);
  group.style.setProperty("--sliding-tab-opacity", "1");
  group.style.setProperty("--mail-status-highlight-x", `${Math.round(x)}px`);
  group.style.setProperty("--mail-status-highlight-width", `${Math.round(buttonRect.width)}px`);
  group.style.setProperty("--mail-status-highlight-opacity", "1");
  if (snap) {
    void group.offsetWidth;
    group.classList.remove("is-sliding-tabs-snapping");
  }
}

function updateSlidingTabs(root = document, snap = false) {
  const scope = root instanceof Element ? root : document;
  const groups = scope.matches?.("[data-sliding-tabs]")
    ? [scope]
    : Array.from(scope.querySelectorAll("[data-sliding-tabs]"));
  groups.forEach((group) => {
    const activeButton =
      group.querySelector("[data-sliding-tab].is-active") ||
      group.querySelector("[data-sliding-tab][aria-pressed='true']");
    updateSlidingTabGroup(group, activeButton, snap);
  });
}

function parseDashboardChartData(rawValue, fallback) {
  if (!rawValue) return fallback;
  try {
    return JSON.parse(rawValue);
  } catch {
    return fallback;
  }
}

function ensureDashboardChartsReady(onReady) {
  return typeof window.Chart !== "undefined";
}

function initDashboardDistribution(root = document) {
  const scope = root instanceof Element ? root : document;
  const section = scope.querySelector("[data-dashboard-distribution]");
  if (!section) return;
  if (!ensureDashboardChartsReady(() => initDashboardCharts(document))) return;

  const canvas = section.querySelector("#categoryDonut");
  const center = section.querySelector("#donutCenter");
  if (!canvas) return;
  if (window.categoryDonutChart) {
    window.categoryDonutChart.destroy();
    window.categoryDonutChart = null;
  }

  const categories = parseDashboardChartData(section.dataset.chartCategories, []);
  const counts = parseDashboardChartData(section.dataset.chartCounts, {});
  const palette = parseDashboardChartData(section.dataset.chartPalette, []);
  const total = Number(section.dataset.chartTotal || 0);
  const neutralColor = "#000000";

  function dataFor(nextCounts) {
    return categories.map((category) => Number(nextCounts[category] || 0));
  }

  function syncCenter(label, value, color = neutralColor) {
    if (!center) return;
    const strong = center.querySelector("strong");
    const span = center.querySelector("span");
    if (strong) {
      strong.textContent = `${value}건`;
      strong.style.color = color;
    }
    if (span) {
      span.textContent = label;
      span.style.color = color;
    }
  }

  syncCenter("전체", total);
  window.categoryDonutChart = new window.Chart(canvas, {
    type: "doughnut",
    data: {
      labels: categories,
      datasets: [{
        data: dataFor(counts),
        backgroundColor: palette.slice(0, categories.length),
        borderColor: "#ffffff",
        borderWidth: 4,
        hoverOffset: 8,
        spacing: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "72%",
      radius: "92%",
      animation: { duration: 500, easing: "easeOutQuart" },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label(ctx) {
              const value = Number(ctx.parsed || 0);
              const currentTotal = Number(section.dataset.chartTotal || 0);
              const pct = currentTotal ? Math.round((value / currentTotal) * 100) : 0;
              return ` ${ctx.label}: ${value}건 (${pct}%)`;
            },
          },
        },
      },
      onHover(_, elements) {
        if (!elements.length) {
          syncCenter(window.dashboardDistributionScope === "all" ? "전체" : "오늘", Number(section.dataset.chartTotal || 0));
          return;
        }
        const index = elements[0].index;
        const label = categories[index] || "";
        const value = Number(window.categoryDonutChart?.data?.datasets?.[0]?.data?.[index] || 0);
        syncCenter(label, value, palette[index] || neutralColor);
      },
    },
  });

  function applyScope(nextScope) {
    const scopeName = nextScope === "all" ? "all" : "today";
    window.dashboardDistributionScope = scopeName;
    const nextCounts = parseDashboardChartData(scopeName === "all" ? section.dataset.chartCountsAll : section.dataset.chartCountsToday, {});
    const nextTotal = Number(scopeName === "all" ? section.dataset.chartTotalAll || 0 : section.dataset.chartTotalToday || 0);
    section.dataset.chartCounts = JSON.stringify(nextCounts);
    section.dataset.chartTotal = String(nextTotal);
    window.categoryDonutChart.data.datasets[0].data = dataFor(nextCounts);
    window.categoryDonutChart.update();
    syncCenter(scopeName === "all" ? "전체" : "오늘", nextTotal);
    section.querySelectorAll("[data-dashboard-distribution-list]").forEach((list) => {
      list.classList.toggle("is-hidden", list.dataset.dashboardDistributionList !== scopeName);
    });
    section.querySelectorAll("[data-dashboard-distribution-scope]").forEach((button) => {
      const active = button.dataset.dashboardDistributionScope === scopeName;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  section.querySelectorAll("[data-dashboard-distribution-scope]").forEach((button) => {
    if (button.dataset.reactChartBound === "true") return;
    button.dataset.reactChartBound = "true";
    button.addEventListener("click", () => applyScope(button.dataset.dashboardDistributionScope || "today"));
  });
  applyScope(window.dashboardDistributionScope || "today");
}

function initDashboardCategoryTimeline(root = document) {
  const scope = root instanceof Element ? root : document;
  const section = scope.querySelector("[data-dashboard-category-timeline]");
  if (!section) return;
  if (window.categoryTimelineChart) {
    window.categoryTimelineChart.destroy();
    window.categoryTimelineChart = null;
  }
  if (!ensureDashboardChartsReady(() => initDashboardCharts(document))) return;

  const canvas = section.querySelector("#categoryTimeline");
  const categories = parseDashboardChartData(section.dataset.chartCategories, []);
  const palette = parseDashboardChartData(section.dataset.chartPalette, []);
  const labels = parseDashboardChartData(section.dataset.chartTimelineLabels, []);
  const datasets = parseDashboardChartData(section.dataset.chartTimelineDatasets, {});
  if (!canvas || !labels.length) return;

  window.categoryTimelineState = window.categoryTimelineState || { hiddenCategories: {} };
  window.categoryTimelineChart = new window.Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: categories.map((category, index) => ({
        label: category,
        data: Array.isArray(datasets[category]) ? datasets[category] : [],
        backgroundColor: `${palette[index] || "#64748b"}33`,
        borderColor: palette[index] || "#64748b",
        borderWidth: 1.5,
        borderRadius: 0,
        borderSkipped: false,
        maxBarThickness: 18,
        categoryPercentage: 0.7,
        barPercentage: 0.9,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      layout: { padding: { left: 0, right: 8, top: 6, bottom: 0 } },
      scales: {
        x: { grid: { display: false, drawBorder: false }, ticks: { color: "#526273", font: { size: 13, weight: 700 } } },
        y: { beginAtZero: true, ticks: { precision: 0, color: "#7a8796", font: { size: 11 } }, grid: { color: "rgba(11, 79, 168, 0.08)", drawBorder: false } },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#17324d",
          padding: 10,
          cornerRadius: 10,
          callbacks: { label: (ctx) => ` ${ctx.dataset.label}: ${ctx.parsed.y}건` },
        },
      },
    },
  });

  function syncLegend() {
    section.querySelectorAll("[data-timeline-category-toggle]").forEach((button) => {
      const category = button.dataset.timelineCategoryToggle || "";
      const visible = !window.categoryTimelineState.hiddenCategories[category];
      button.classList.toggle("is-inactive", !visible);
      button.setAttribute("aria-pressed", visible ? "true" : "false");
      const index = window.categoryTimelineChart.data.datasets.findIndex((dataset) => dataset.label === category);
      if (index >= 0) window.categoryTimelineChart.setDatasetVisibility(index, visible);
    });
    window.categoryTimelineChart.update();
  }

  section.querySelectorAll("[data-timeline-category-toggle]").forEach((button) => {
    if (button.dataset.reactChartBound === "true") return;
    button.dataset.reactChartBound = "true";
    button.addEventListener("click", (event) => {
      event.preventDefault();
      const category = button.dataset.timelineCategoryToggle || "";
      if (!category) return;
      const hidden = window.categoryTimelineState.hiddenCategories;
      hidden[category] = !hidden[category];
      syncLegend();
    });
  });
  syncLegend();
}

function initDashboardRoutingOverview(root = document) {
  const scope = root instanceof Element ? root : document;
  const section = scope.querySelector("[data-dashboard-routing-overview]");
  if (!section) return;
  function applyScope(nextScope) {
    const scopeName = nextScope === "all" ? "all" : "today";
    window.dashboardRoutingScope = scopeName;
    let activeTotal = 0;
    section.querySelectorAll("[data-dashboard-routing-panel]").forEach((panel) => {
      const active = panel.dataset.dashboardRoutingPanel === scopeName;
      panel.classList.toggle("is-hidden", !active);
      if (active) activeTotal = Number(panel.dataset.dashboardRoutingTotal || 0);
    });
    section.querySelectorAll("[data-dashboard-routing-scope]").forEach((button) => {
      const active = button.dataset.dashboardRoutingScope === scopeName;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    const totalLabel = section.querySelector("[data-dashboard-routing-scope-total]");
    if (totalLabel) totalLabel.textContent = `총 ${activeTotal}건`;
  }
  section.querySelectorAll("[data-dashboard-routing-scope]").forEach((button) => {
    if (button.dataset.reactChartBound === "true") return;
    button.dataset.reactChartBound = "true";
    button.addEventListener("click", () => applyScope(button.dataset.dashboardRoutingScope || "today"));
  });
  applyScope(window.dashboardRoutingScope || "today");
}

function initDashboardCharts(root = document) {
  initDashboardDistribution(root);
  initDashboardCategoryTimeline(root);
  initDashboardRoutingOverview(root);
}

function Sidebar({ activeView, items, onSelect }) {
  return h(
    "aside",
    { className: "sidebar" },
    h(
      "div",
      { className: "brand" },
      h("span", { className: "brand-mark" }, "CoRA"),
      h("div", { className: "brand-copy" }, h("strong", null, "CoRA Mail"), h("span", null, "Corporate Routing Assistant")),
    ),
    h(
      "nav",
      { className: "nav", "aria-label": "Main navigation" },
      items.map((view) =>
        h(
          "button",
          {
            key: view,
            type: "button",
            className: activeView === view ? "active" : "",
            "aria-label": `${VIEW_TITLES[view]} 탭 열기`,
            onClick: () => onSelect(view),
          },
          h(MaterialIcon, null, VIEW_ICONS[view]),
          VIEW_TITLES[view],
        ),
      ),
    ),
  );
}

function SlidingModeTabs({ options, activeValue, onSelect }) {
  const rootRef = useRef(null);

  useEffect(() => {
    const snap = () => updateSlidingTabs(rootRef.current, true);
    window.requestAnimationFrame(snap);
    const timeout = window.setTimeout(snap, 300);
    document.fonts?.ready?.then(snap).catch(() => null);
    window.addEventListener("resize", snap);
    return () => {
      window.clearTimeout(timeout);
      window.removeEventListener("resize", snap);
    };
  }, [activeValue, options]);

  return h(
    "div",
    { ref: rootRef, className: "mode-selector", role: "group", "aria-label": "메일 데이터 소스 선택", "data-sliding-tabs": true },
    h("span", { className: "mode-selector-pill", "data-sliding-tabs-pill": true, "aria-hidden": "true" }),
    (options || []).map((option) =>
      h(
        "button",
        {
          key: option.value,
          className: `mode-option${option.value === activeValue ? " is-active" : ""}`,
          type: "button",
          "data-sliding-tab": true,
          title: `${option.label} 데이터 보기`,
          "aria-label": `${option.label} 데이터 보기`,
          "aria-pressed": option.value === activeValue ? "true" : "false",
          onClick: (event) => {
            updateSlidingTabGroup(rootRef.current, event.currentTarget);
            onSelect(option.value);
          },
        },
        h("span", { className: "mode-option-label" }, option.label),
      ),
    ),
  );
}

function Topbar({ state, activeView, onModeChange, onOpenSettings }) {
  const accountBanner = state.demoMode
    ? h(
        "div",
        { className: "gmail-account-banner is-demo", title: state.gmailConnectedAccount },
        h(MaterialIcon, null, "mail"),
        h("span", { className: "gmail-account-value mono" }, state.gmailConnectedAccount),
      )
    : h(
        "button",
        {
          className: "gmail-account-banner",
          type: "button",
          title: `${state.mailProviderLabel} Mail 동기화 설정`,
          "aria-label": `${state.mailProviderLabel} Mail 동기화 설정 열기`,
          onClick: onOpenSettings,
        },
        h(MaterialIcon, null, "mail"),
        h("span", { className: "gmail-account-value mono" }, state.gmailConnectedAccount),
      );

  return h(
    "header",
    { className: "topbar" },
    h("div", { className: "topbar-heading" }, h("div", { className: "title", id: "pageTitle" }, VIEW_TITLES[activeView] || "Dashboard"), accountBanner),
    h(
      "div",
      { className: "top-actions" },
      h(SlidingModeTabs, { options: state.displayModeOptions || [], activeValue: state.displayMode, onSelect: onModeChange }),
      h("a", { className: "icon-btn", href: "/docs", title: "API Docs", "aria-label": "API 문서 열기" }, h(MaterialIcon, null, "api")),
      h("span", { className: "current-user" }, state.currentUser),
      h(
        "form",
        { className: "logout-form", method: "post", action: "/logout" },
        h("button", { className: "icon-btn", type: "submit", title: "Logout", "aria-label": "로그아웃" }, h(MaterialIcon, null, "logout")),
      ),
      h("div", { className: "avatar" }, "AI"),
    ),
  );
}

function FragmentPanel({ html, busy, error, panelRef }) {
  if (error) {
    return h(
      "main",
      { className: "content" },
      h("div", { className: "empty-state" }, h(MaterialIcon, null, "error"), h("strong", null, "화면을 불러오지 못했습니다."), h("p", null, error)),
    );
  }
  return h("main", {
    className: "content",
    id: "main-panel",
    ref: panelRef,
    "aria-busy": busy ? "true" : "false",
    dangerouslySetInnerHTML: { __html: html },
  });
}

function MailSettingsModal({ state, open, html, onClose, bodyRef }) {
  if (state.demoMode) return null;
  return h(
    "div",
    { className: "gmail-settings-modal", id: "gmailSettingsModal", role: "dialog", "aria-modal": "true", "aria-labelledby": "gmailSettingsTitle", hidden: !open },
    h("div", { className: "gmail-settings-backdrop", onClick: onClose }),
    h(
      "section",
      { className: "gmail-settings-dialog", tabIndex: "-1" },
      h(
        "header",
        { className: "gmail-settings-dialog-head" },
        h("div", null, h("h2", { id: "gmailSettingsTitle" }, `${state.mailProviderLabel} Mail 계정 연동 설정`)),
        !state.mailProviderSetupRequired &&
          h("button", { className: "icon-btn", type: "button", onClick: onClose, "aria-label": `${state.mailProviderLabel} Mail 동기화 설정 닫기` }, h(MaterialIcon, null, "close")),
      ),
      h("div", { className: "gmail-settings-dialog-body", ref: bodyRef, dangerouslySetInnerHTML: { __html: html } }),
    ),
  );
}

function ConfirmModal({ confirm, onCancel, onSubmit }) {
  return h(
    "div",
    { className: "manual-route-confirm-modal", id: "manualRouteConfirmModal", role: "dialog", "aria-modal": "true", hidden: !confirm },
    h("div", { className: "manual-route-confirm-backdrop", onClick: onCancel }),
    h(
      "section",
      { className: "manual-route-confirm-dialog", tabIndex: "-1" },
      h("div", { className: "manual-route-confirm-icon", "aria-hidden": "true" }, h(MaterialIcon, null, confirm?.icon || "forward_to_inbox")),
      h("div", { className: "manual-route-confirm-content" }, h("p", { className: "manual-route-confirm-eyebrow" }, confirm?.eyebrow || "확인"), h("h2", null, confirm?.title || "진행할까요?"), h("p", null, confirm?.message || "")),
      h("div", { className: "manual-route-confirm-actions" }, h("button", { className: "btn manual-route-confirm-secondary", type: "button", onClick: onCancel }, "취소"), h("button", { className: "btn manual-route-confirm-primary", type: "button", onClick: onSubmit }, h(MaterialIcon, null, confirm?.icon || "check"), h("span", null, confirm?.submitLabel || "확인"))),
    ),
  );
}

function CopyToast({ message }) {
  return h("div", { className: `copy-toast${message ? " is-visible" : ""}`, role: "status", "aria-live": "polite", "aria-atomic": "true", hidden: !message }, message || "복사됐습니다.");
}

function LoadingPanel({ view }) {
  return h(
    "main",
    { className: "content", id: "main-panel", "aria-busy": "true" },
    h(
      "section",
      { className: "view page-view" },
      h(
        "div",
        { className: "empty-state empty-state-inline", role: "status", "aria-live": "polite" },
        h(MaterialIcon, null, "progress_activity"),
        h("strong", null, `${VIEW_TITLES[view] || "화면"} 화면을 불러오는 중`),
      ),
    ),
  );
}

function useReactFragmentRuntime({ setActiveView, setHtml, setError, setConfirm, showToast, openMailSettings }) {
  const inputTimers = useRef(new WeakMap());
  const submitRequest = useCallback(
    async (element, options = {}) => {
      const method = options.method || (element.getAttribute("hx-post") ? "POST" : "GET");
      const rawUrl = options.url || element.getAttribute("hx-post") || element.getAttribute("hx-get") || element.getAttribute("action") || "/";
      const url = new URL(rawUrl, window.location.origin);
      const target = options.target || targetFor(element);
      const swap = options.swap || element.getAttribute("hx-swap") || "innerHTML";
      const form = element.tagName === "FORM" ? element : element.closest("form");
      const bodyPairs = [...parseHxVals(element), ...includedPairs(element)];
      const init = { method, headers: requestHeaders(), credentials: "same-origin" };
      if (method.toUpperCase() === "GET") {
        for (const [key, value] of formBody(form, bodyPairs).entries()) url.searchParams.set(key, value);
      } else {
        init.headers = { ...init.headers, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" };
        init.body = formBody(form, bodyPairs).toString();
      }
      const response = await fetch(url.toString(), init);
      dispatchHxTriggers(response);
      const redirect = response.headers.get("HX-Redirect");
      if (redirect) {
        window.location.assign(redirect);
        return;
      }
      if (response.status === 401) {
        window.location.assign("/login?next=/");
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      if (swap === "none") return;
      const text = await response.text();
      if (target?.id === "main-panel") {
        setHtml(text);
        const view = viewForUrl(url.toString());
        if (view) {
          setActiveView(view);
          window.history.replaceState(null, "", `/?view=${encodeURIComponent(view)}`);
        }
        return;
      }
      swapTarget(target, text, swap);
      window.setTimeout(() => {
        loadTriggerElements(document).forEach((node) => {
          if (node.dataset.reactLoadFired === "true") return;
          node.dataset.reactLoadFired = "true";
          submitRequest(node).catch((loadError) => setError(loadError.message || "Request failed"));
        });
      }, 0);
    },
    [setActiveView, setConfirm, setError, setHtml],
  );

  useEffect(() => {
    const onClick = (event) => {
      const trigger = event.target?.closest?.("[data-gmail-settings-open], [data-gmail-open-advanced], [data-assignee-editor-toggle], [data-category-filter], [data-mail-status-filter], [data-search-example], [data-copy-business-ref], [hx-get], [hx-post]");
      const favoriteButton = event.target?.closest?.("[data-mail-favorite-toggle]");
      if (favoriteButton) {
        event.preventDefault();
        event.stopPropagation();
        toggleFavoriteMail(favoriteButton);
        return;
      }
      if (!trigger) return;
      const clickedMailRow = trigger.closest?.("#mailRows .clickable-row[data-email-uid], #dashboardMailRows .clickable-row[data-email-uid]");
      replayMailRowClickTransition(clickedMailRow);
      if (trigger.matches("[data-gmail-settings-open]")) {
        event.preventDefault();
        openMailSettings();
        return;
      }
      if (trigger.matches("[data-gmail-open-advanced]")) {
        event.preventDefault();
        document.querySelectorAll(".gmail-advanced-setup, .gmail-token-setup").forEach((node) => {
          node.open = true;
          node.classList.remove("is-hidden");
        });
        return;
      }
      if (trigger.matches("[data-assignee-editor-toggle]")) {
        event.preventDefault();
        const id = trigger.dataset.assigneeEditorId || "";
        document.querySelectorAll(`[data-assignee-editor-row='${CSS.escape(id)}']`).forEach((row) => row.classList.toggle("is-hidden"));
        return;
      }
      if (trigger.matches("[data-category-filter]")) {
        event.preventDefault();
        const value = trigger.dataset.categoryFilter === "__all__" ? "" : trigger.dataset.categoryFilter || "";
        const input = document.getElementById("categoryFilter");
        if (input) input.value = value;
        const label = document.querySelector("[data-category-filter-selected-label]");
        if (label) label.textContent = value || "업무 유형 전체";
        trigger.closest("[data-category-filter-select]")?.removeAttribute("open");
        submitRequest(document.getElementById("mailRows") || trigger).catch((error) => setError(error.message || "Request failed"));
        return;
      }
      if (trigger.matches("[data-mail-status-filter]")) {
        event.preventDefault();
        const targetName = trigger.dataset.mailStatusTarget || "";
        const status = trigger.dataset.mailStatusFilter || "";
        const input = document.getElementById(targetName === "dashboard" ? "dashboardWorkStatusFilter" : "workStatusFilter");
        if (input) input.value = status;
        trigger.closest(".mail-status-filter")?.querySelectorAll("[data-mail-status-filter]").forEach((button) => {
          const active = button === trigger;
          button.classList.toggle("is-active", active);
          button.setAttribute("aria-pressed", active ? "true" : "false");
        });
        updateSlidingTabGroup(trigger.closest(".mail-status-filter"), trigger);
        if (targetName === "dashboard") {
          const url = new URL("/ui/mail-rows", window.location.origin);
          url.searchParams.set("view", "dashboard");
          if (status) url.searchParams.set("status", status);
          const categoryState = document.querySelector("[data-category-filter-selected-label]")?.textContent?.trim();
          if (categoryState && categoryState !== "업무 유형 전체") url.searchParams.set("category", categoryState);
          fetch(url.toString(), { headers: requestHeaders(), credentials: "same-origin" })
            .then((response) => {
              if (!response.ok) throw new Error(`HTTP ${response.status}`);
              return response.text();
            })
            .then((text) => {
              const rows = document.getElementById("dashboardMailRows");
              if (rows) {
                rows.innerHTML = text;
                hydrateFavoriteMailButtons(rows);
                initializeProgressToggles(rows);
              }
              window.requestAnimationFrame(() => {
                hydrateFavoriteMailButtons(document);
                updateSlidingTabs(document, true);
              });
            })
            .catch((error) => setError(error.message || "Request failed"));
          return;
        }
        submitRequest(document.getElementById("mailRows") || trigger).catch((error) => setError(error.message || "Request failed"));
        return;
      }
      if (trigger.matches("[data-search-example]")) {
        event.preventDefault();
        const input = document.querySelector(trigger.dataset.searchInput || "#searchQueryInput");
        if (input) {
          input.value = trigger.dataset.searchExample || "";
          input.closest("form")?.requestSubmit();
        }
        return;
      }
      if (trigger.matches("[data-copy-business-ref]")) {
        event.preventDefault();
        const value = trigger.dataset.copyBusinessRef || trigger.textContent.trim();
        navigator.clipboard?.writeText(value).catch(() => null);
        showToast("업무번호가 복사됐습니다.");
        return;
      }
      if (!trigger.matches("[hx-get], [hx-post]")) return;
      event.preventDefault();
      if (trigger.matches("[data-work-in-progress-toggle].t-toggle")) {
        const activeValue = trigger.closest("form")?.querySelector("input[name='active']")?.value || "";
        const nextOn = activeValue ? activeValue === "true" : trigger.dataset.on !== "true";
        trigger.classList.add("is-init");
        trigger.dataset.on = nextOn ? "true" : "false";
        trigger.setAttribute("aria-checked", nextOn ? "true" : "false");
      }
      const message = trigger.getAttribute("hx-confirm");
      if (message) {
        setConfirm({ element: trigger, message, title: trigger.dataset.mailDeleteButton ? "메일을 삭제할까요?" : "진행할까요?", submitLabel: trigger.dataset.mailDeleteButton ? "삭제" : "확인", icon: trigger.dataset.mailDeleteButton ? "delete" : "check" });
        return;
      }
      submitRequest(trigger).catch((error) => setError(error.message || "Request failed"));
    };
    const onSubmit = (event) => {
      const form = event.target;
      if (!form?.matches?.("[hx-get], [hx-post]")) return;
      event.preventDefault();
      const progressToggle = form.querySelector("[data-work-in-progress-toggle].t-toggle");
      if (progressToggle) {
        const activeValue = form.querySelector("input[name='active']")?.value || "";
        const nextOn = activeValue ? activeValue === "true" : progressToggle.dataset.on !== "true";
        progressToggle.classList.add("is-init");
        progressToggle.dataset.on = nextOn ? "true" : "false";
        progressToggle.setAttribute("aria-checked", nextOn ? "true" : "false");
      }
      submitRequest(form).catch((error) => setError(error.message || "Request failed"));
    };
    const onChange = (event) => {
      const element = event.target;
      if (!element?.matches?.("[hx-trigger*='change'][hx-get], [hx-trigger*='change'][hx-post]")) return;
      submitRequest(element).catch((error) => setError(error.message || "Request failed"));
    };
    const onInput = (event) => {
      const element = event.target;
      if (!element?.matches?.("[hx-trigger*='keyup'][hx-get], [hx-trigger*='input'][hx-get], [hx-trigger*='keyup'][hx-post], [hx-trigger*='input'][hx-post]")) return;
      const previous = inputTimers.current.get(element);
      if (previous) window.clearTimeout(previous);
      const timer = window.setTimeout(() => {
        submitRequest(element).catch((error) => setError(error.message || "Request failed"));
      }, 450);
      inputTimers.current.set(element, timer);
    };
    document.addEventListener("click", onClick);
    document.addEventListener("submit", onSubmit);
    document.addEventListener("change", onChange);
    document.addEventListener("input", onInput);
    document.addEventListener("keyup", onInput);
    document.addEventListener("click", handleFavoriteMailClick, true);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("submit", onSubmit);
      document.removeEventListener("change", onChange);
      document.removeEventListener("input", onInput);
      document.removeEventListener("keyup", onInput);
      document.removeEventListener("click", handleFavoriteMailClick, true);
    };
  }, [openMailSettings, setConfirm, setError, showToast, submitRequest]);

  return submitRequest;
}

function App() {
  const [state] = useState(initialState);
  const [activeView, setActiveView] = useState(state.activeView || "dashboard");
  const [html, setHtml] = useState(initialViewHtml);
  const [error, setError] = useState("");
  const [viewLoading, setViewLoading] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsHtml, setSettingsHtml] = useState("");
  const [confirm, setConfirm] = useState(null);
  const [toast, setToast] = useState("");
  const abortRef = useRef(null);
  const panelRef = useRef(null);
  const settingsBodyRef = useRef(null);
  const items = useMemo(() => navItems(state), [state]);

  const showToast = useCallback((message) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 1400);
  }, []);

  const loadView = useCallback((view) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setError("");
    setViewLoading(true);
    setHtml("");
    fetch(VIEW_ENDPOINTS[view] || VIEW_ENDPOINTS.dashboard, {
      method: "POST",
      headers: requestHeaders(),
      credentials: "same-origin",
      signal: controller.signal,
    })
      .then((response) => {
        if (response.status === 401) {
          window.location.assign("/login?next=/");
          return "";
        }
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.text();
      })
      .then((text) => {
        if (controller.signal.aborted) return;
        setHtml(text);
        setViewLoading(false);
      })
      .catch((fetchError) => {
        if (fetchError.name === "AbortError") return;
        setError(fetchError.message || "Unknown error");
        setViewLoading(false);
      });
  }, []);

  const loadSettings = useCallback(() => {
    fetch(state.mailSettingsPanelUrl || "/ui/settings/gmail-sync", { headers: requestHeaders(), credentials: "same-origin" })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.text();
      })
      .then(setSettingsHtml)
      .catch((fetchError) => setSettingsHtml(`<div class="empty-state"><strong>설정을 불러오지 못했습니다.</strong><p>${fetchError.message}</p></div>`));
  }, [state.mailSettingsPanelUrl]);

  const openMailSettings = useCallback(() => {
    setSettingsOpen(true);
    loadSettings();
  }, [loadSettings]);

  const submitRequest = useReactFragmentRuntime({ setActiveView, setHtml, setError, setConfirm, showToast, openMailSettings });

  const selectView = useCallback(
    (view) => {
      setActiveView(view);
      window.history.replaceState(null, "", `/?view=${encodeURIComponent(view)}`);
      loadView(view);
    },
    [loadView],
  );

  const changeMode = useCallback((displayMode) => {
    fetch(`/ui/display-mode/toggle?display_mode=${encodeURIComponent(displayMode)}`, {
      method: "POST",
      headers: requestHeaders(),
      credentials: "same-origin",
    }).then((response) => {
      if (response.ok) window.location.assign(`/?view=${encodeURIComponent(activeView)}`);
    });
  }, [activeView]);

  const confirmSubmit = useCallback(() => {
    const element = confirm?.element;
    setConfirm(null);
    if (element) submitRequest(element).catch((error) => setError(error.message || "Request failed"));
  }, [confirm, setError, submitRequest]);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => {
    const root = panelRef.current;
    if (!root) return;
    hydrateFavoriteMailButtons(root);
    initializeProgressToggles(root);
    updateSlidingTabs(root, true);
    initDashboardCharts(root);
    loadTriggerElements(root).forEach((element) => {
      if (element.dataset.reactLoadFired === "true") return;
      element.dataset.reactLoadFired = "true";
      submitRequest(element).catch((loadError) => setError(loadError.message || "Request failed"));
    });
  }, [html, submitRequest]);

  useEffect(() => {
    const root = settingsBodyRef.current;
    if (!root) return;
    const snap = () => updateSlidingTabs(root, true);
    window.requestAnimationFrame(snap);
    const timeout = window.setTimeout(snap, 300);
    document.fonts?.ready?.then(snap).catch(() => null);
    loadTriggerElements(root).forEach((element) => {
      if (element.dataset.reactLoadFired === "true") return;
      element.dataset.reactLoadFired = "true";
      submitRequest(element).catch((loadError) => setSettingsHtml(`<div class="empty-state"><strong>설정을 불러오지 못했습니다.</strong><p>${loadError.message}</p></div>`));
    });
    return () => window.clearTimeout(timeout);
  }, [settingsOpen, settingsHtml, submitRequest]);

  return h(
    "div",
    { className: "app-shell" },
    h(Sidebar, { activeView, items, onSelect: selectView }),
    h(
      "section",
      { className: "main" },
      h(Topbar, { state, activeView, onModeChange: changeMode, onOpenSettings: openMailSettings }),
      viewLoading && !error ? h(LoadingPanel, { view: activeView }) : h(FragmentPanel, { html, busy: !html, error, panelRef }),
    ),
    h(MailSettingsModal, { state, open: settingsOpen, html: settingsHtml, onClose: () => setSettingsOpen(false), bodyRef: settingsBodyRef }),
    h(ConfirmModal, { confirm, onCancel: () => setConfirm(null), onSubmit: confirmSubmit }),
    h(CopyToast, { message: toast }),
  );
}

createRoot(document.getElementById("react-root")).render(h(App));
