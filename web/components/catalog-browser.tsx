"use client";

import { useEffect, useState } from "react";

type Item = {
  id: string;
  record_key: string;
  category: string;
  region: string;
  brand: string;
  family: string;
  manufacturer_part_number: string | null;
  status: string;
  missing_key_facts: boolean;
};

type Catalog = {
  items: Item[];
  data_version: string | null;
  empty_reason: string | null;
  next_cursor: string | null;
};

export function CatalogBrowser() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState(false);
  const [query, setQuery] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(
      async () => {
        setError(false);
        try {
          const search = new URLSearchParams({ limit: "20" });
          if (query.trim()) search.set("q", query.trim());
          const response = await fetch(`/api/v1/catalog/products?${search}`, {
            cache: "no-store",
            signal: controller.signal,
          });
          if (!response.ok) throw new Error("Catalog unavailable");
          setCatalog(await response.json());
        } catch (reason) {
          if ((reason as Error).name !== "AbortError") setError(true);
        }
      },
      query ? 200 : 0,
    );
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [attempt, query]);

  return (
    <main className="catalog-page">
      <a className="catalog-back" href="/">
        ← 返回需求页
      </a>
      <header className="catalog-heading">
        <p>已发布目录</p>
        <h1>商品与报价依据</h1>
        <span>
          {catalog?.data_version
            ? `数据版本 ${catalog.data_version.slice(0, 8)}`
            : "当前没有已发布的真实目录"}
        </span>
      </header>
      <label className="catalog-search">
        搜索精确型号、品牌或已登记别名
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="例如：厂商料号"
          maxLength={120}
        />
      </label>
      {error ? (
        <section role="alert" className="catalog-message">
          目录暂时不可用。
          <button onClick={() => setAttempt((value) => value + 1)}>
            重新连接
          </button>
        </section>
      ) : !catalog ? (
        <section role="status" className="catalog-message">
          正在读取已发布版本…
        </section>
      ) : catalog.items.length === 0 ? (
        <section role="status" className="catalog-message">
          <h2>尚无可公开的商品</h2>
          <p>只有经过来源许可、证据核验和版本发布的精确 SKU 才会出现在这里。</p>
        </section>
      ) : (
        <ul className="catalog-list" aria-label="商品目录">
          {catalog.items.map((item) => (
            <li key={item.id}>
              <a href={`/catalog/${item.id}`}>
                <span>
                  {item.category} · {item.region}
                </span>
                <h2>
                  {item.brand} {item.family}
                </h2>
                <p>{item.manufacturer_part_number || "料号待披露"}</p>
                <small>
                  {item.missing_key_facts ? "关键规格仍有缺失" : "规格已附证据"}
                </small>
              </a>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
