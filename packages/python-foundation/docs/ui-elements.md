# HTML 요소와 CSS 클래스 사용

`python_foundation.ui_assets.asset_path`는 설치된 wheel의 `ui.css`, `ui.js`, `showcase.html`만 반환합니다. FastAPI에서는 이 파일을 명시적인 정적 라우트로 제공하세요. 입력받은 임의 경로를 전달하지 않습니다. 앱과 공통 요소는 같은 origin에서 동작하고 외부 폰트·CDN이 필요 없습니다.

```python
from fastapi.responses import FileResponse
from python_foundation.ui_assets import asset_path


@app.get("/assets/ui.css")
def ui_css():
    return FileResponse(asset_path("ui.css"), media_type="text/css")
```

CSS를 먼저 로드하고 `ui.js`를 `defer`로 앱 스크립트보다 먼저 로드합니다.

```html
<ui-page-header heading="지식 라이브러리" description="저장한 지식을 확인하세요."></ui-page-header>
<button class="ui-button ui-button--primary">검색</button>
<label class="ui-field">검색어<input class="ui-input" type="search"></label>
<ui-badge tone="success">저장 완료</ui-badge>
<ui-empty-state heading="검색 결과가 없습니다" description="검색어를 바꿔보세요." icon="search"></ui-empty-state>
```

커스텀 요소는 light DOM에 네이티브 HTML을 구성하며 Shadow DOM을 쓰지 않습니다. 제목과 설명을 바꾸면 다시 그립니다. `ui-page-header`는 페이지당 하나의 h1, 빈 상태는 h3를 생성하므로 주변 섹션에 h2를 둡니다. 배지의 tone은 neutral/success/info/warning/danger입니다. 컴포넌트는 자체 키보드 동작을 재구현하지 않고 button·dialog 등 네이티브 요소를 사용합니다.

```js
const row = FoundationUI.record({
  title: item.title,
  meta: [FoundationUI.badge("결정", "info"), item.category],
  preview: item.summary,
  onSelect: () => openItem(item)
});
list.append(row);
```

FoundationUI는 element/icon/badge/record/emptyState를 제공합니다. 문자열은 textContent로 표시합니다. record는 type=button인 네이티브 버튼이며 `aria-current=true`로 선택을 표시합니다. emptyState는 선택적으로 `{label, run}` 동작을 받습니다. 유효하지 않은 배지 tone과 아이콘 이름에는 기본 표현을 사용합니다.

공통 클래스는 `.ui-button`, `.ui-input`, `.ui-panel`, `.ui-field`, `.ui-tabs`, `.ui-pager`, `.ui-badge`, `.ui-record`, `.ui-empty-state`, `.ui-dialog`, `.ui-prose`입니다. 앱별 레이아웃은 앱 CSS에 둡니다. ui.css는 기본 문서·컨트롤 스타일도 지정하므로 기존 앱에는 스타일 충돌을 확인한 뒤 도입하세요. Showcase는 지식 앱의 `/knowledge/components`에서 확인하며, HTML 파일 안의 자산 URL은 소비 앱에서 사용하는 경로에 맞춰야 합니다.
