import { Planner } from "@/components/planner";

export default function Home() {
  return (
    <>
      <header className="site-header">
        <a className="wordmark" href="/" aria-label="选机有据首页">
          <span className="brand-icon">选</span>选机有据
          <span className="edition">开发预览</span>
        </a>
        <a className="header-link" href="#principles">
          推荐原则 <span aria-hidden="true">↗</span>
        </a>
      </header>
      <main>
        <section className="hero">
          <div className="eyebrow">
            <span />
            从需求出发 · 用证据选择
          </div>
          <h1>
            选一台适合你的电脑，
            <br />
            <em>先把需求说清楚。</em>
          </h1>
          <p className="hero-copy">
            预算花在哪里，配置为什么合适，哪些信息还待核实。
            <br className="desktop-break" />
            每一步都应该看得明白。
          </p>
          <div className="market">
            <span>中国大陆</span>
            <span>人民币 CNY</span>
            <span>全新零售商品</span>
          </div>
        </section>
        <Planner />
        <section
          className="principles"
          id="principles"
          aria-labelledby="principles-title"
        >
          <div className="section-heading">
            <span className="section-kicker">我们的推荐原则</span>
            <h2 id="principles-title">答案要有依据，未知也要说明。</h2>
          </div>
          <div className="principle-grid">
            <article>
              <span className="principle-number">01 / 预算清楚</span>
              <h3>每一笔费用都算进去</h3>
              <p>区分商品、运费和服务费用。缺少报价时，不把未知当成零元。</p>
            </article>
            <article>
              <span className="principle-number">02 / 配置核验</span>
              <h3>匹配型号，也检查条件</h3>
              <p>精确到具体配置与地区。兼容性缺少证据时，明确列出待核实项。</p>
            </article>
            <article>
              <span className="principle-number">03 / 来源可查</span>
              <h3>知道依据来自哪里</h3>
              <p>规格和报价分别注明来源与时间。不虚构跑分，也不承诺最低价。</p>
            </article>
          </div>
        </section>
      </main>
      <footer>
        <span>选机有据 · 让选择更有把握</span>
        <span>开发预览 · 尚不提供购买清单</span>
      </footer>
    </>
  );
}
