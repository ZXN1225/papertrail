from uuid import uuid4

from app.knowledge.service import bm25, tokenize


def chunk(content):
    return {"id": uuid4(), "content": content}


def test_bm25_ranks_exact_part_number_and_chinese_terms_deterministically():
    exact, general = chunk("TEST-CPU-9000 支持 DDR5 内存。"), chunk("内存安装说明。")
    ranked = bm25("TEST-CPU-9000 DDR5", [general, exact])
    assert ranked[0][1]["id"] == exact["id"]
    assert tokenize("DDR5 内存") == ["ddr5", "内存"]


def test_bm25_returns_no_claim_when_terms_do_not_match():
    assert bm25("PCIe6", [chunk("DDR5 内存安装说明")]) == []


def test_bm25_stable_tie_breaks_by_chunk_id():
    first, second = chunk("DDR5"), chunk("DDR5")
    ranked = bm25("DDR5", [second, first])
    assert [item[1]["id"] for item in ranked] == sorted([first["id"], second["id"]], key=str)
