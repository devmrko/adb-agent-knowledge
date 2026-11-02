"""Opt-in SDK experiment. No production MCP/backend replacement or schema reset."""

import argparse
import asyncio
import json
import logging
import re
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
import oracledb
from dotenv import dotenv_values
from oracleagentmemory.apis.embedders import IEmbedder
from oracleagentmemory.core import MemoryExtractionConfig, OracleAgentMemory, SchemaPolicy


class ApplicationEmbedder(IEmbedder):
    embedding_dimension = 1024
    max_input_tokens = 8192

    def __init__(self, python, hf_home):
        self.lock = threading.Lock()
        self.process = subprocess.Popen(
            [python, str(Path(__file__).with_name("embed_worker.py")), "--hf-home", hf_home],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )

    def embed(self, texts, *, is_query=False):
        with self.lock:
            self.process.stdin.write(json.dumps({"texts": texts, "is_query": is_query}) + "\n")
            self.process.stdin.flush()
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("Embedding worker stopped; no vectors returned")
            vectors = np.asarray(json.loads(line), dtype=np.float32)
            if vectors.shape != (len(texts), 1024) or not np.isfinite(vectors).all():
                raise ValueError("Invalid embedding output")
            return vectors

    async def embed_async(self, texts, *, is_query=False):
        return await asyncio.to_thread(self.embed, texts, is_query=is_query)

    def close(self):
        self.process.terminate()
        self.process.wait(timeout=30)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--env-file", required=True)
    p.add_argument("--expected-user", required=True)
    p.add_argument("--store-id", required=True)
    p.add_argument("--embedding-python", required=True)
    p.add_argument("--hf-home", required=True)
    p.add_argument("--report", required=True)
    a = p.parse_args()
    if not re.fullmatch(r"(VKV_|OAM_TEST_)[A-Z0-9_]+", a.expected_user):
        p.error("Expected user must be an isolated VKV_ or OAM_TEST_ account")
    if not re.fullmatch(r"OAMEVAL_[A-Z0-9_]{1,8}", a.store_id):
        p.error("Store ID must be isolated OAMEVAL_ prefix, at most 16 characters")
    cfg = dotenv_values(a.env_file)
    if cfg.get("USER_NAME", "").upper() != a.expected_user:
        p.error("Configuration account does not match expected isolated user")
    logging.getLogger("oracleagentmemory").setLevel(logging.ERROR)
    pool = oracledb.create_pool(
        user=cfg["USER_NAME"],
        password=cfg["USER_PASSWORD"],
        dsn=cfg["ORACLE_DSN"],
        config_dir=cfg["WALLET_DIR"],
        wallet_location=cfg["WALLET_DIR"],
        wallet_password=cfg["WALLET_PASSWORD"],
        min=1,
        max=3,
        increment=1,
        tcp_connect_timeout=10,
        retry_count=0,
    )
    embedder = ApplicationEmbedder(a.embedding_python, a.hf_home)
    report = {"sdk": "26.8.0", "store_id": a.store_id, "extraction": False, "checks": {}, "queries": []}
    try:
        with pool.acquire() as con:
            with con.cursor() as cur:
                cur.execute("select user from dual")
                assert cur.fetchone()[0] == a.expected_user
                report["database_version"] = con.version
                cur.execute(
                    "select object_name from user_objects where object_name like 'VK_%' order by object_name"
                )
                before = cur.fetchall()
        print("CONNECT PASS", report["database_version"], flush=True)
        started = time.perf_counter()
        memory = OracleAgentMemory(
            connection=pool,
            embedder=embedder,
            memory_store_id=a.store_id,
            schema_policy=SchemaPolicy.CREATE_IF_NECESSARY,
            memory_extraction_config=MemoryExtractionConfig(extract_memories=False),
        )
        report["setup_seconds"] = round(time.perf_counter() - started, 3)
        print("SDK SETUP PASS", flush=True)
        # Unique IDs per run avoid overwriting earlier observations; no cleanup/reset.
        run = str(time.time_ns())
        user = "oam-demo-" + run
        texts = {
            "old": "테스트 프로젝트의 배포 서버는 서버 A다. 이전 운영 기록이다.",
            "new": "테스트 프로젝트의 배포 서버를 서버 B로 변경했다. 현재 배포 서버는 B다.",
            "deadline": "신규 직원 안내: 본인의 복지 신청 기한을 지킬 책임이 있다. 재직자의 가입 자격은 이 자료로 판단할 수 없다.",
            "claim1": "미확정 자료 A는 재택근무 신청 승인자가 팀장이라고 설명한다.",
            "claim2": "미확정 자료 B는 재택근무 신청 승인자가 부서장이라고 설명한다.",
        }
        ids = {}
        for key, content in texts.items():
            ids[key] = memory.add_memory(
                content,
                memory_type="fact",
                user_id=user,
                memory_id=run + "-" + key,
                autonomous_linking=False,
                metadata={"fixture": "synthetic", "scope": "oam-evaluation", "run": run},
            )
        alien = memory.add_memory(
            "다른 사용자의 배포 서버는 비공개 서버 C다.",
            memory_type="fact",
            user_id=user + "-other",
            autonomous_linking=False,
        )
        memory.link_records(ids["new"], "fact", ids["old"], "fact", "supersedes")
        memory.link_records(ids["claim2"], "fact", ids["claim1"], "fact", "contradicts")
        report["checks"]["explicit_writes_and_links"] = True
        report["user_id"] = user
        report["ids"] = ids
        for query, expected in [
            ("현재 배포 서버는 어디인가?", "new"),
            ("복지 신청 기한 책임은 누구에게 있는가?", "deadline"),
            ("재택근무 승인자는 누구인가?", "claim1"),
        ]:
            started = time.perf_counter()
            results = memory.search(
                query,
                user_id=user,
                max_results=2,
                include_invalid_results=False,
                num_hops=2,
                max_linked_results=10,
            )
            rows = []
            for result in results:
                linked = getattr(result, "linked_results", [])
                rows.append(
                    {
                        "id": result.id,
                        "content": result.content,
                        "status": str(getattr(result.record, "status", None)),
                        "linked": [
                            {
                                "id": x.id,
                                "content": x.content,
                                "status": str(getattr(x.record, "status", None)),
                            }
                            for relation, x in linked
                        ],
                    }
                )
            direct = [x["id"] for x in rows]
            assert ids[expected] in direct, "Expected result absent"
            assert ids["old"] not in direct, "Superseded memory leaked as current result"
            assert alien not in direct and all(alien not in [z["id"] for z in x["linked"]] for x in rows), (
                "User isolation failure"
            )
            report["queries"].append(
                {"query": query, "seconds": round(time.perf_counter() - started, 3), "rows": rows}
            )
            print("SEARCH PASS", query, flush=True)
        links = [z["id"] for q in report["queries"] for x in q["rows"] for z in x["linked"]]
        report["checks"]["historical_link_visible"] = ids["old"] in links
        report["checks"]["contradicting_memories_both_current"] = all(
            i in [x["id"] for x in report["queries"][2]["rows"]] for i in [ids["claim1"], ids["claim2"]]
        )
        report["checks"]["scoped_current_search"] = True
        with pool.acquire() as con:
            with con.cursor() as cur:
                cur.execute(
                    "select object_name from user_objects where object_name like 'VK_%' order by object_name"
                )
                assert cur.fetchall() == before
                cur.execute(
                    "select object_type, count(*) from user_objects where object_name like :prefix group by object_type",
                    prefix=a.store_id + "_%",
                )
                report["managed_objects"] = dict(cur.fetchall())
        report["checks"]["existing_vk_object_inventory_unchanged"] = True
        report["user_id"] = user
        report["ids"] = ids
        report["status"] = "PASS" if all(report["checks"].values()) else "PARTIAL"
    except Exception as exc:
        report["status"] = "FAILED"
        report["error_type"] = type(exc).__name__
        # Do not emit provider messages, credentials or SQL.
        report["oracle_error_code"] = getattr(exc.args[0], "full_code", None) if exc.args else None
        raise
    finally:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(json.dumps(report, ensure_ascii=False, indent=2))
        embedder.close()
        pool.close()
        print("REPORT", report["status"], a.report, flush=True)


if __name__ == "__main__":
    main()
