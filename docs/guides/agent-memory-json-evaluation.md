# 업무 지식의 Agent Memory JSON 저장 검토

2026-11-03 · Oracle Agent Memory 26.8.0 · **검증용 실험, 운영 이관 아님**

## 판단

업무 지식을 JSON 구조로 Agent Memory에 저장하고 필요한 키로 필터링하는 방향은 가능하다.
이를 경험/선호 전용 저장소로 한정할 이유는 없다. 다만 JSON 저장 성공이 원문 버전·RDF·근거
기능까지 대체했다는 뜻은 아니다. **공통 저장 기반 후보로 채택하고 제한된 이관 실험을 진행할 가치가 있다.**
운영 전체 전환은 아직 권하지 않는다.

## 실제 확인한 것

분리된 테스트 계정과 JPROBE 접두사 SDK 저장소에 한글·이모지 합성 자료만 저장했다.
운영 AKMEMORY와 vk_* 데이터는 변경하지 않았다. 테스트 자료는 삭제하지 않고 남겼다.

| 항목 | 결과 |
|---|---|
| JSON 문자열 본문 왕복 | 원문과 json.loads 결과가 동일 |
| JSON metadata 왕복 | 중첩 객체·배열·한글·이모지 보존 |
| 저장 크기 | 약 1KB, 32KB, 256KB, 1MiB, 4MiB 모두 성공 |
| 최대 시험 본문 | UTF-8 4,194,350 bytes, Python 문자 수 1,290,608 |
| 최대 시험 metadata | UTF-8 JSON 직렬화 4,194,397 bytes |
| 키 조건 검색 | 중첩 review.status와 배열 tags의 원소 조건 성공 |
| 소유자 제한 | 다른 테스트 사용자 목록은 빈 결과 |
| 벡터 검색 + metadata 조건 | 조건에 맞는 레코드 반환 |
| 저장 내용과 검색 텍스트 분리 | JSON 본문 유지, 지정한 검색 청크만 임베딩 경로에 전달 |
| metadata 변경 | 전체 객체 교체. 지정하지 않은 기존 키는 사라짐. 임베딩 호출 없음 |
| 본문/검색 텍스트 변경 | 새 본문 보존, 새 검색 텍스트로 임베딩 호출 |
| 실제 DB 색인 확인 | 이전 청크가 새 청크 1개로 교체되고 저장 벡터가 새 입력의 계산값과 일치 |
| SQL JSON 키 조건 | JSON_VALUE(metadata, '$.review.status') 조건 조회 성공 |
| memory에 Python dict 직접 전달 | ValueError. json.dumps로 문자열 직렬화해야 함 |
| 현재 앱 입력 제한 | MemorySave.text는 12,000자 허용, 12,001자 거부 |

이 실험은 합성 벡터로 저장·조회 경로를 확인했다. 한국어 의미 검색 품질이나 실제 모델의
장문 처리·속도를 검증한 결과가 아니다. 대용량 JSON은 저장 본문과 metadata 양쪽에 같은
합성 payload를 넣어 각각 왕복 확인했으며, 이중 저장을 제품 설계로 권장하는 것은 아니다.

## 용량을 구분해야 한다

- **현재 MCP/API:** 본문 12,000자. 임의 JSON metadata를 입력하는 공개 필드는 아직 없다.
- **시험한 SDK 저장:** 본문·metadata 각각 약 4MiB까지 성공. 최대 허용치를 찾은 것은 아니다.
- **Oracle JSON 자료형:** 공식 한도 32MB. UTF-8 JSON 문자열의 바이트 수와 내부 이진 JSON 크기는
  동일하지 않으므로 HTTP 요청 32MB를 그대로 허용한다는 뜻이 아니다.
- **CLOB 본문:** JSON 자료형 32MB 제한과 별개다. SDK/드라이버/요청 제한과 자원 소모도 따져야 한다.
- **임베딩:** 모델 입력 토큰 한도는 저장 용량과 별개다. 큰 JSON을 한 벡터로 보내면 안 된다.

첫 실행에서 1MiB/4MiB의 본문+metadata 저장·읽기는 각각 약27.5초/21.9초였다.
각1회, 로컬→원격DB, 합성 벡터·짧은 index_text 조건이며 성능 기준으로 일반화할 수 없다.
크기 증가와 지연이 단조롭지 않으므로 반복/부하 측정 없이 최대치로 운영 용량을 정하지 않는다.

## 제안하는 저장 규약

전체 원문은 content JSON 문자열에 한 번 저장하고, 필터에 필요한 짧은 키는 metadata로 둔다.
검색용 텍스트는 요약만이 아니라 상세의 각 절차/섹션도 포함한 청크로 만든다.
metadata의 변경된 값이 의미 검색에도 필요하면 index_text를 다시 만들어 갱신해야 한다.

```python
payload = {
    "schema_version": 1,
    "summary": "Tasteby 배포 절차",
    "sections": [
        {"id": "precheck", "title": "사전 확인", "text": "..."},
        {"id": "release", "title": "배포", "text": "..."},
    ],
    "sources": [{"kind": "git", "location": "<원본 위치>", "version": "<commit>"}],
}
metadata = {
    "kind": "procedure",
    "project": "tasteby",
    "knowledge_id": "<논리 지식 ID>",
    "revision_id": "<원문 버전 ID>",
    "review": {"status": "confirmed"},
    "schema_version": 1,
}
store.add(
    record_type="memory",
    record_ids="<버전별 레코드 ID>",
    user_ids="<인증 소유자 ID>",
    contents=[json.dumps(payload, ensure_ascii=False)],
    metadata=metadata,
    index_texts=[["Tasteby · 배포 절차 · 사전 확인 ...", "Tasteby · 배포 절차 · 배포 ..."]],
)
store.list(
    "memory",
    user_id="<인증 소유자 ID>",
    metadata_filter={"project": "tasteby", "review": {"status": "confirmed"}},
)
```

코드는 SDK 저장 수준 예제다. 현재 memory_save MCP가 이 필드를 받는다는 뜻이 아니다.
소유자·권한·스키마·버전·용량 검증은 API에서 수행해야 한다. 사용자가 준 metadata로 소유자를 정하면 안 된다.

## 기존 기능과의 대응

| 기존 기능 | Agent Memory 기반에서 필요한 것 |
|---|---|
| 원문/요약/출처 | content JSON 규약과 검증 |
| 청크/벡터 저장 | index_texts로 기존 청크 정책 전달 가능. 실제 임베딩 비교 추가 필요 |
| 정확한 버전과 이력 | update_memory 덮어쓰기만으로 대체 불가. 버전별 새 레코드 + 현재 버전 포인터 필요 |
| 수정 충돌/멱등성 | 현재 애플리케이션 보호 유지 필요 |
| 인덱스 문서/분류 | metadata와 기존 인덱스 연결을 매핑하고 페이징·수정 시 동작 검증 |
| RDF/업무 대상 관계 | SDK 기억 관계와 의미가 다름. 기존 그래프 유지 및 근거 버전 매핑 필요 |
| 정확한 인용·원문 변경 재검토 | 근거 테이블과 outbox 처리의 키/이벤트 계약 보존 필요 |
| 키워드 혼합 검색 | 현재 앱의 LIKE+벡터 방식과 SDK 방식은 다름. 동일 동작으로 간주하면 안 됨 |

SDK HYBRID 검색은 공식 문서상 OracleDBEmbedder를 요구한다. 현재 외부 한국어 임베딩을 그대로
사용하면서 SDK HYBRID만 켜는 방식은 지원 조건과 맞지 않는다. 저장 통합과 검색 방식 변경은 별도 검증한다.

**다음 판단 기준:** 작은 문서3건의 이전/새 버전을 SDK에 적재하여 기존 검색 결과·정확한 인용·
관계 현재성·재시도/충돌·되돌리기를 비교한다. 같은 본문을 두 운영 저장소에 영구 중복 보관하지 않는다.
이 실험 통과 전에는 기존 지식이나 그래프 테이블을 삭제하지 않는다.

## 재현

```sh
./uvw sync --extra agent-memory
./.venv/bin/python -m scripts.probe_agent_memory_json \
  --env-file /path/to/isolated-test.env \
  --store-id JPROBE11031355 \
  --output .run/json-probe/result.json
```

테스트 계정은 VKV_/OAM_TEST_ 접두사를 요구한다. 스토어 생성 DDL과 테스트 데이터 저장이 발생한다.
비밀 설정이나 사용자 원문을 결과에 출력하지 않는다. mapping_content_support의 FAIL/ValueError는
객체 직접 입력이 지원되지 않았다는 관찰이다. 다른 FAIL은 결과를 확인하기 전 성공으로 해석하지 않는다.

## 공식 근거

- [Store writes: content/index_text, metadata filters](https://docs.oracle.com/en/database/oracle/agent-memory/26.8/guide/api/stores.html)
- [Agent Memory: update_memory와 검색 설정](https://docs.oracle.com/en/database/oracle/agent-memory/26.8/guide/api/agentmemory.html)
- [Oracle 자료형 한도](https://docs.oracle.com/en/database/oracle/oracle-database/26/refrn/datatype-limits.html)

검증: ruff/format/mypy, 기존 테스트290개 통과. 원시 합성 시험 결과는 [JSON 결과](../reference/agent-memory-json-probe.json)에 보관한다.
