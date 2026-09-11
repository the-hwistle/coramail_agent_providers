# CoRA Mail Design System

## Purpose

This document defines the durable visual, interaction, and information-design rules for CoRA Mail.

It is the design source of truth for developers and coding agents working on user-facing UI.

Use this document to decide:

- what information should be emphasized
- how operational states should be represented
- when existing UI patterns should be reused
- how AI-generated information differs from source information
- when a new component or visual convention is justified

This document does not replace the implementation.

Existing templates, shared macros, CSS components, and verified UI behavior remain the implementation reference.

## Product Context

CoRA Mail is an enterprise operational workspace for understanding incoming business email, identifying required work, assigning the appropriate person, and following that work through completion.

It is not a marketing dashboard.

It is not primarily an analytics product.

The interface exists to help users answer operational questions quickly:

1. 어떤 메일이 들어왔는가?
2. 어떤 업무가 필요한가?
3. 현재 어떤 상태인가?
4. 누가 맡아야 하는가?
5. 왜 그 담당자가 추천되었는가?
6. 담당자가 실제로 업무를 시작했는가?
7. 실제 회신 또는 필요한 조치가 이루어졌는가?
8. 지금 사람이 확인해야 할 예외는 무엇인가?

## Primary Users

### 업무 담당자

Needs to quickly identify:

- 새로 배정된 업무
- 아직 확인하지 않은 업무
- 진행 중인 업무
- 회신한 업무
- 완료할 업무
- 지연되거나 주의가 필요한 업무

### 업무 관리자

Needs to quickly identify:

- 미배정 업무
- 담당자별 현재 업무 상태
- 지연 업무
- 긴급 업무
- 사람이 검토해야 하는 AI 판단
- 반복되는 실패 또는 병목

### AI 운영·개발 담당자

Needs to distinguish:

- 원본 데이터
- AI 생성 결과
- 검색·판단 근거
- 모델 실행 상태
- 실패 상태
- 사용자 확정값과 수정 이력

## Design Principles

### Operational clarity over decoration

업무 상태와 필요한 행동을 장식 요소보다 우선한다.

Prefer:

- clear hierarchy
- compact tables
- explicit labels
- predictable controls
- restrained surfaces

### Scan first, inspect second

목록에서는 많은 업무를 빠르게 훑을 수 있어야 한다.

Detailed information should appear after selection rather than expanding every row.

Use:

- tables
- concise row metadata
- master/detail layouts
- drawers or detail panels

Do not turn every record into a large card.

### State must be immediately understandable

Operational state is a primary information dimension.

Users should not need to open an email to understand whether work is:

- 미확인
- 진행중
- 회신함
- 완료
- 지연
- 실패
- 검토 필요

State must always include text. Never communicate state by color alone.

### Evidence before confidence theater

AI recommendations should expose their basis when available.

Prefer:

- concise reasoning
- retrieved evidence
- source references
- candidate comparison
- explicit review state

Avoid:

- decorative confidence gauges
- unexplained percentages
- AI-looking animation used only for visual effect

### Source and AI output must remain distinguishable

Visually distinguish:

1. original mail content
2. attachment content
3. extracted factual information
4. AI-generated summaries/classifications
5. retrieved evidence
6. system state
7. human-confirmed information

### Progressive disclosure

Show the minimum information needed for the current decision.

Examples:

- mail row -> mail detail
- attachment -> extracted fields
- routing recommendation -> reasoning/evidence
- monitoring row -> inspector
- assignee work row -> detail drawer

### Consistency before novelty

Before creating a new UI component:

1. search the existing implementation
2. identify an existing pattern with the same semantic purpose
3. reuse it when possible
4. extend it only for a genuine variant
5. create a new component only when no existing component represents the interaction

Do not create visually similar duplicates.

## Interface Character

CoRA Mail should feel:

- operational
- precise
- restrained
- trustworthy
- information-dense
- calm under high workload

It should resemble an enterprise work console rather than a marketing SaaS website.

Prefer:

- flat or lightly elevated surfaces
- compact spacing
- clear borders
- strong text hierarchy
- restrained blue emphasis
- neutral background hierarchy
- data tables
- fixed navigation
- explicit operational states

Avoid:

- marketing-style hero sections
- decorative gradients
- gradient text
- glassmorphism
- excessive blur
- glow effects
- oversized cards
- large unused whitespace
- decorative illustrations
- floating widgets without an operational purpose
- excessive rounded containers
- decorative charts
- colored icon backgrounds without semantic meaning

## Application Shell

Preserve the established application shell unless product information architecture explicitly changes.

### Sidebar

Use the persistent primary navigation for major product areas.

Do not introduce competing primary navigation.

### Topbar

Use for:

- current page identity
- connected account context
- global mode/account actions
- current user
- global utilities

Do not place page-specific workflow actions in the global topbar without a clear reason.

## Layout Patterns

### Dashboard

Recommended hierarchy:

1. high-level operational metrics
2. meaningful distribution/trend
3. routing/workload overview
4. current mail stream

Metrics should help users decide what needs attention. Prefer operational metrics such as 미확인, 확인함, 진행중, 지연, 미배정, 사람 검토 필요, 실패, and 오늘 완료 over decorative KPI tiles.

### Inbox

Preserve the master/detail pattern.

List information priority:

1. work/read state
2. sender
3. subject
4. business category
5. assignee
6. received time

### Assignments / My Work

Preserve:

- workload/status rail
- work list
- selected work detail

Counts are navigation/prioritization aids, not vanity KPIs. The primary states are 미확인, 확인함, 진행중, 회신함, 완료, 지연, and 검토 필요.

### Monitoring

Prioritize:

- stage
- failure
- delay
- assignment
- processing state
- inspectability

Horizontal scrolling and resizable columns are acceptable when operational information requires them.

## Information Density

CoRA Mail is desktop-first.

Prefer compact but readable density.

Typical size tendencies:

- 11px auxiliary/table metadata
- 12-13px normal operational UI
- 16px section title
- 20px page/app title
- 24px major heading where needed
- 28px operational metric

Do not enlarge text or whitespace only to make the UI feel modern.

## Typography

Primary:
`Pretendard Variable`

Use monospace only when structure benefits from it:

- identifiers
- technical values
- exact timestamps when alignment matters
- account/email values
- model/trace IDs

Do not use monospace decoratively.

User-facing Korean UI should normally remain Korean.

## Design Tokens

The token system exists to prevent individual features from creating separate visual conventions.

New UI should use semantic tokens rather than arbitrary values.

Existing UI does not need a repository-wide rewrite solely to adopt these tokens.

Recommended semantic tokens:

- Brand
  - `--color-brand: #06182f`
  - `--color-action: #0058be`
  - `--color-action-hover: #004b9f`
- Selection
  - `--color-selected-bg: #eff6ff`
  - `--color-selected-border: #bfdbfe`
- Surface
  - `--color-bg: #fbf9fb`
  - `--color-surface: #ffffff`
  - `--color-surface-subtle: #f8fafc`
- Border
  - `--color-border: #d7d5d8`
  - `--color-border-subtle: #e2e8f0`
- Text
  - `--color-text: #1b1b1d`
  - `--color-text-strong: #0f172a`
  - `--color-text-secondary: #475569`
  - `--color-text-muted: #64748b`
- General semantic state
  - `--color-info: #0058be`
  - `--color-warning: #b66e00`
  - `--color-danger: #ba1a1a`
  - `--color-success: #0f7a49`
- Work state
  - `--status-unacknowledged: #ef4444`
  - `--status-in-progress: #f59e0b`
  - `--status-responded: #22c55e`
  - `--status-completed: #64748b`
- Radius
  - `--radius-control: 6px`
  - `--radius-surface: 8px`
  - `--radius-pill: 999px`
- Spacing
  - `--space-1: 4px`
  - `--space-2: 8px`
  - `--space-3: 12px`
  - `--space-4: 16px`
  - `--space-5: 20px`
  - `--space-6: 24px`
- Typography
  - `--font-xs: 11px`
  - `--font-sm: 12px`
  - `--font-md: 13px`
  - `--font-lg: 16px`
  - `--font-xl: 20px`
  - `--font-2xl: 24px`
  - `--font-metric: 28px`
- Elevation
  - `--shadow-surface: 0 8px 22px rgba(15, 23, 42, .04)`
  - `--shadow-overlay: 0 24px 60px rgba(15, 23, 42, .16)`

### Token Rules

The dark navy shell is part of the established CoRA Mail identity.

Do not introduce another ordinary action/selection blue when `--color-action` or selection tokens represent the same meaning.

Do not treat `#2563eb` or other currently scattered blue values as additional design-system primitives.

Work-state colors are operational indicators and are not interchangeable with generic success/warning/error colors.

## Radius

Preferred vocabulary:

- control: 6px
- surface: 8px
- pill: 999px

Do not introduce new 14px / 16px / 18px / 20px card radii in workspace UI.

Existing larger radii may remain until their affected feature is intentionally revised.

## Spacing

New layouts should primarily use:
4 / 8 / 12 / 16 / 20 / 24px

Existing 6 / 10 / 14 / 18px values do not need global migration.

## Elevation

Use border/surface hierarchy for ordinary workspace separation.

Use subtle surface shadow sparingly.

Use stronger elevation for:

- drawers
- dialogs
- popovers
- temporary overlays

Do not apply large SaaS-style shadow to every panel.

## Status Semantics

### `assigned` - 미확인

Assigned but the assignee has not indicated that work has started.

Use attention semantics, not application-error semantics. `미확인` may use red attention treatment, but it does not mean the application failed.

### `in_progress` - 진행중

Work has started or reply initiation has begun.

### `responded` - 회신함

Actual outbound message has been observed in the linked Gmail thread after reply initiation.

This does not necessarily mean the entire work item is complete.

### `completed` - 완료

The assignee explicitly marked the work item complete.

### `overdue` - 지연

Derived condition.

Do not replace the underlying state.

Prefer:
`진행중 · 지연`

### System / AI Processing State

Do not confuse work execution state with AI or system processing state.

Examples of separate system states:

- `queued`
- `running`
- `failed`
- `cancelled`
- `review_required`

## General State Colors

General meaning:

- blue/info -> selection or informational active state
- amber/warning -> waiting, attention, delay, progress
- red/danger -> failure, destructive action, urgent intervention
- green/success -> verified successful terminal state
- slate/neutral -> inactive, historical or low-attention state

Do not use red simply because an item is important.

Do not use green before success has actually occurred.

## Surfaces

### Panel

Use for major sections.

Default:

- subtle border
- white or neutral surface
- small radius
- little/no shadow

### Card

Use only when an item genuinely behaves as an independent unit.

Do not wrap every section in a card.

### Drawer / Overlay

Use for temporary inspection that should preserve the current work context.

Stronger elevation is acceptable.

## Buttons

Primary action:
main action in the current context.

Avoid multiple competing primary actions in a small region.

Danger:
only for destructive operations.

Icon-only controls must have an accessible label.

## Filters

Keep filters close to affected data.

Reuse existing patterns.

Segmented controls:

- small mutually exclusive option sets
- frequent switching

Dropdown:

- longer option sets

Do not create page-specific filter variants without need.

## Tables

Tables are a primary CoRA Mail pattern.

Rules:

- explicit columns
- subject/primary identity visually dominant
- truncate long values when necessary
- full detail available elsewhere
- selected row visually clear
- sticky header preferred for long tables
- horizontal scroll acceptable when required
- resize behavior must remain stable where already implemented

Do not replace dense operational tables with oversized cards solely for aesthetics.

## Chips and Badges

Use for:

- category
- status
- routing role
- compact filter state

Do not turn ordinary metadata into pills for decoration.

Category styling and operational-state styling should remain semantically distinguishable.

## Mail Content

Original email content is source material.

It should visually read as source content, not as an AI card.

Preserve:

- sender
- timestamp
- subject
- body
- attachments

## Attachments

Communicate:

- filename
- document type when known
- availability
- size where useful
- view/download
- extracted information

Detailed extraction can be collapsible.

Missing/unsupported/failed attachment states must use explicit text.

## AI-Generated Information

Clearly indicate AI/system origin where appropriate.

Examples:

- summary
- classification
- extracted interpretation
- routing recommendation
- reasoning

Expose when applicable:

- source
- current state
- evidence
- review requirement
- retry/regeneration state

AI results must not look like part of the original email. AI recommendations must not be presented as confirmed organizational facts.

When an AI routing recommendation exists, prefer this hierarchy:

1. 추천 담당자
2. current routing/review state
3. concise recommendation reason
4. supporting evidence
5. whether human review is required

Do not create UI rules that expose raw chain-of-thought-like internal reasoning.

## Human Review

Human review is first-class.

When review is required:

- say confirmation is needed
- explain what needs confirmation
- preserve original AI output
- distinguish human-confirmed result
- expose relevant evidence

Human review is a normal product state, not an error screen.

## AI Progress and Failure

Examples of explicit operation labels:

- 메일 유형 재분류 중
- 핵심 요청 재생성 중
- 첨부파일 재분석 중

Avoid decorative AI loading effects unrelated to actual progress.

On failure:

- clearly state failure
- preserve usable existing data
- provide retry when supported
- do not imply unrelated states failed

## Empty States

Use clear operational wording.

Good:
`현재 조건에 맞는 업무 메일이 없습니다.`

Avoid large promotional illustration-style empty states.

## Interaction States

Define where applicable:

- default
- hover
- focus-visible
- selected
- active
- disabled
- loading
- error

Do not remove focus-visible without an accessible replacement.

## Motion

Motion communicates state change, not decoration.

Use restrained motion for:

- drawers
- modals
- selection
- progress

Avoid:

- bouncing
- unnecessary scale animation
- decorative looping animation

## Responsive Behavior

Desktop-first.

When space becomes limited:

1. preserve essential operational information
2. collapse secondary columns/layouts
3. allow necessary table scrolling
4. move detail surfaces below or into drawers where appropriate

Do not hide critical work state solely to make the screen cleaner.

## Accessibility

New UI should:

- use semantic HTML where practical
- preserve keyboard navigation
- provide visible focus
- label icon-only controls
- provide text equivalents for color states
- preserve sufficient contrast
- use aria state attributes where appropriate

## Language and Content

Use concise Korean by default.

Keep established product/technical terms in English only where clearer.

Avoid vague action labels such as:

- 확인
- 실행
- 작업
- 처리

when a specific verb is available.

Prefer labels such as:

- 새로고침
- 업무 완료
- Gmail에서 회신
- 재분류
- 재분석

## Do

- 기존 컴포넌트와 macro를 먼저 찾는다.
- 업무 상태를 텍스트로 명확히 표시한다.
- 긴 목록은 표 중심으로 구성한다.
- 상세 정보는 필요할 때 보여준다.
- AI 결과와 원본 정보를 구분한다.
- AI 추천 근거에 접근할 수 있게 한다.
- 실제 업무 진행/완료 상태를 단순 누적 건수보다 우선한다.
- 실패와 사람 검토 상태를 정상적인 제품 상태로 다룬다.
- 변경 후 실제 렌더링을 확인한다.

## Don't

Do not introduce without explicit product requirement:

- gradients
- glassmorphism
- glow effects
- oversized rounded cards
- cards around every section
- arbitrary new blue colors
- arbitrary new status colors
- decorative KPI tiles
- decorative charts
- excessive shadows
- hero-like whitespace
- floating decorative UI
- decorative AI sparkle effects
- duplicate components
- new CSS conventions when an existing semantic pattern already exists

## Implementation Rules for Coding Agents

Before user-facing UI changes:

1. Read this file.
2. Inspect the affected existing template/component.
3. Inspect related shared macros and CSS.
4. Search for an existing semantic pattern first.
5. Preserve product workflow unless explicitly changing it.
6. Do not introduce arbitrary color/radius/shadow/type/spacing values.
7. Do not add a new status visual without defining semantics.
8. Do not visually merge AI-generated information with source information.
9. Preserve accessibility behavior.
10. Verify the actual rendered result.

When current implementation conflicts with this document:

- do not redesign unrelated UI
- follow this document for new work
- limit cleanup to affected scope
- preserve verified behavior
- document durable exceptions when genuinely necessary

## Verification

For meaningful UI changes:

- run relevant automated tests
- run relevant Playwright smoke/E2E test
- inspect affected view in a real browser
- verify default/selected/loading/empty/error states where applicable
- verify desktop and narrower layout where relevant
- verify keyboard behavior for drawers/dialogs/menus/filters

For visually significant work, capture before/after screenshots when practical.

Automated test success alone does not prove visual compliance.

## Migration Direction

The frontend currently loads:

- `app.css`
- `app-02.css`
- `app-03.css`
- `app-04.css`

These files contain accumulated and overlapping visual rules.

Do not merge them in this task.

Do not perform repository-wide direct-hex replacement.

Do not globally normalize all old radius values.

Instead:

1. use semantic tokens for new UI
2. migrate affected selectors when touching an existing feature
3. remove duplicates only after checking cascade dependencies
4. preserve behavior
5. visually verify the affected screen

Long-term direction:

- fewer direct hex values
- fewer arbitrary radii
- fewer page-specific visual conventions
- more semantic tokens
- more reuse of shared patterns
