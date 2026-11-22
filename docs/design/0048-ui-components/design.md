# 지식 웹 화면과 Foundation 공통 요소

2026-11-22. 사용자는 유명한 웹 UI 자료를 검색하고, HTML 요소와 CSS 클래스를 공통화해 지식 웹 화면을 개선하도록 요청했다.

## 확인 가능한 완료 조건

- 기존 검색, 카테고리·범위·종류 필터, 인덱스, 페이지 이동, 지식·메모리·관계·사용자 원칙·SQL 조회가 유지된다.
- 왼쪽 저장소 탐색 → 목록 → 상세로 이어지고, 설정·SQL은 선택했을 때만 표시한다.
- 공통 토큰·컨트롤·행·배지·빈 상태·제목은 Foundation의 정적 CSS/JS에서 재사용한다. DOM은 light DOM이며 CSS 클래스로 꾸민다.
- 별도 UI 프레임워크·CDN·폰트 의존성을 추가하지 않는다. 텍스트는 textContent로 렌더링하고 CSP와 인증·CSRF 경계를 유지한다.
- 390px 모바일·데스크톱에서 검색과 상세가 잘리지 않고 키보드 포커스를 확인한다. 실제 API 검증과 합성 미리보기 검증을 구분한다.

## 근거와 적용

- IBM Carbon Data table: 검색·필터·주요 동작을 도구 모음에 모으고 행의 선택 상태와 일관된 밀도로 목록을 표현한다.
  https://www.carbondesignsystem.com/building-blocks/core/components/data-table/guidelines
- Adobe Spectrum App frame: 탐색 영역·전체 동작·선택 항목 동작을 구분하고 본문에 집중한다.
  https://spectrum.adobe.com/foundations/app-frame/overview
- Atlassian Empty state: 빈 이유와 다음 동작을 짧게 안내하고 제목 순서를 지킨다.
  https://atlassian.design/components/empty-state/

참고일 2026-11-22. 공식 패턴을 프로젝트에 맞춰 구현하며 외부 소스·브랜드 에셋을 복제하지 않는다.

## 구조와 계약

기존 Foundation web 모듈과 다른 로컬 checkout의 Redwood UI를 확인했다. 현재 실행 checkout의 Foundation에는 UI 자산이 없어 서버 템플릿 프레임워크를 이식하는 대신 작은 정적 요소 모듈을 추가한다.
`python_foundation.ui_assets.asset_path(name)`은 허용된 자산 경로만 반환한다. ui.css는 `.ui-*` 클래스와 토큰, ui.js는 `FoundationUI`의 안전한 DOM 생성과 `<ui-page-header>`, `<ui-empty-state>`, `<ui-badge>` light DOM 요소를 제공한다. 반복 렌더링은 자식 노드를 중복 생성하지 않는다.
기존 common.css는 앱 프레임, style.css는 지식·메모리 상세를 담당한다. 공통 UI 배포물은 wheel에 포함한다. 새 자산은 명시적 공개 정적 라우트로만 제공한다. 기존 DOM ID와 HTTP 데이터 계약은 유지한다.
사용자 원칙 dialog는 네이티브 모달, Escape·닫기·포커스 복귀를 지원한다. 사용자가 승인 버튼을 누르는 기존 저장 경로만 유지한다.
모바일은 단일 열과 상세 뒤로가기를 제공하며, 보이지 않는 목록에 키보드 포커스가 남지 않도록 한다.

## 검증

필수 Ruff·format·mypy·pytest 및 Foundation wheel 빌드·격리 설치 검증. 추가로 컴포넌트 자산 허용 목록, 기존 DOM ID 보존, 검색·상세 전환·모달·모바일·빈 결과·안전한 텍스트 렌더링을 브라우저에서 확인한다.
