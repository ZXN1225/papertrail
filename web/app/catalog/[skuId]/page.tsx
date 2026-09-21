"use client";

import { useEffect, useState } from "react";

type Evidence = {
  source_name: string;
  document_title: string;
  canonical_url: string;
};
type Fact = {
  id: string;
  key: string;
  description: string;
  value: string | number | boolean | null;
  unit: string;
  evidence: Evidence;
};
type Offer = {
  id: string;
  merchant_name: string;
  amount_minor: number | null;
  shipping_minor: number | null;
  tax_minor: number | null;
  tax_included: boolean | null;
  freshness: string;
  expires_at: string;
};
type Product = {
  brand: string;
  family: string;
  manufacturer_part_number: string | null;
  record_key: string;
  facts: Fact[];
};

function yuan(amount: number | null) {
  return amount === null ? "待核实" : `¥${(amount / 100).toFixed(2)}`;
}

export default function CatalogProductPage({
  params,
}: {
  params: Promise<{ skuId: string }>;
}) {
  const [product, setProduct] = useState<Product | null>(null);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let active = true;
    params
      .then(async ({ skuId }) => {
        const [detail, quote] = await Promise.all([
          fetch(`/api/v1/catalog/products/${skuId}`, { cache: "no-store" }),
          fetch(`/api/v1/catalog/products/${skuId}/offers`, {
            cache: "no-store",
          }),
        ]);
        if (!active) return;
        if (!detail.ok) {
          setMissing(true);
          return;
        }
        setProduct(await detail.json());
        if (quote.ok) setOffers((await quote.json()).items);
      })
      .catch(() => active && setMissing(true));
    return () => {
      active = false;
    };
  }, [params]);

  return (
    <main className="catalog-page">
      <a className="catalog-back" href="/catalog">
        ← 返回已发布目录
      </a>
      {missing ? (
        <section className="catalog-message">
          <h1>商品尚未发布</h1>
          <p>该精确 SKU 不在当前公开版本中。</p>
        </section>
      ) : !product ? (
        <section role="status" className="catalog-message">
          正在读取商品证据…
        </section>
      ) : (
        <>
          <header className="catalog-heading">
            <p>{product.record_key}</p>
            <h1>
              {product.brand} {product.family}
            </h1>
            <span>{product.manufacturer_part_number || "料号待披露"}</span>
          </header>
          <section className="catalog-detail">
            <h2>已核验规格</h2>
            {product.facts.length === 0 ? (
              <p>当前版本没有可公开的已核验规格。</p>
            ) : (
              <dl>
                {product.facts.map((fact) => (
                  <div key={fact.id}>
                    <dt>{fact.description}</dt>
                    <dd>
                      {String(fact.value ?? "未披露")}
                      {fact.unit ? ` ${fact.unit}` : ""}
                      <a
                        href={fact.evidence.canonical_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {fact.evidence.source_name} ·{" "}
                        {fact.evidence.document_title}
                      </a>
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </section>
          <section className="catalog-detail">
            <h2>当前人工报价快照</h2>
            {offers.length === 0 ? (
              <p>没有符合当前性、地区、库存和资格要求的报价。</p>
            ) : (
              <ul>
                {offers.map((offer) => (
                  <li key={offer.id}>
                    <strong>{offer.merchant_name}</strong>
                    <span>
                      {yuan(offer.amount_minor)}，运费{" "}
                      {yuan(offer.shipping_minor)}，
                      {offer.tax_included
                        ? "含税"
                        : `税费 ${yuan(offer.tax_minor)}`}
                    </span>
                    <small>
                      有效至{" "}
                      {new Date(offer.expires_at).toLocaleString("zh-CN")}
                    </small>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </main>
  );
}
