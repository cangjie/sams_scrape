const test = require("node:test");
const assert = require("node:assert");
const L = require("./lib.js");

const items = [
  { id: "a1", n: "Member’s Mark 饮用天然水", s: "1.5L*8", d: "源自天然水源" },
  { id: "a2", n: "MM 有机小米", s: "2.3kg", d: "东北产区" },
  { id: "a3", n: "洋河 海之蓝", s: "1L", d: "浓香型白酒" },
];

test("normalize 统一全角半角、大小写、撇号和空白", () => {
  assert.strictEqual(L.normalize("  ＭＭ　有机 "), "mm 有机");
  assert.strictEqual(L.normalize("Member’s"), "member's");
});

test("tokens 按空格分词，空查询没有词", () => {
  assert.deepStrictEqual(L.tokens(" 洋河  1l "), ["洋河", "1l"]);
  assert.deepStrictEqual(L.tokens("   "), []);
});

test("search 每个词都要命中名字、规格或卖点", () => {
  assert.deepStrictEqual(L.search(items, "member's 天然水").results.map(i => i.id), ["a1"]);
  assert.deepStrictEqual(L.search(items, "ＭＭ 小米").results.map(i => i.id), ["a2"]);
  assert.deepStrictEqual(L.search(items, "洋河 1L").results.map(i => i.id), ["a3"]);
  assert.deepStrictEqual(L.search(items, "白酒").results.map(i => i.id), ["a3"]);
  assert.strictEqual(L.search(items, "茅台").total, 0);
  assert.deepStrictEqual(L.search(items, "   "), { results: [], total: 0 });
});

test("search 最多返回 LIMIT 条，total 是全部命中数", () => {
  const many = Array.from({ length: 250 }, (_, i) => ({ id: "a" + i, n: "牛奶 " + i, s: "", d: "" }));
  const r = L.search(many, "牛奶");
  assert.strictEqual(r.results.length, L.LIMIT);
  assert.strictEqual(r.total, 250);
});

test("searchMessage：没有结果、结果太多、正常", () => {
  assert.strictEqual(L.searchMessage(" 茅台 ", 0), "没有找到「茅台」");
  assert.strictEqual(L.searchMessage("牛奶", 250), "结果太多，请再加一个词（共 250 个）");
  assert.strictEqual(L.searchMessage("牛奶", 12), "");
});

test("searchHref：空查询回首页，其余编码后进搜索页", () => {
  assert.strictEqual(L.searchHref("   "), "#/");
  assert.strictEqual(L.searchHref(" 洋河 1L "), "#/s/" + encodeURIComponent("洋河 1L"));
});

test("parseRoute 识别四种页面，乱写的回首页，编码坏了不报错", () => {
  assert.deepStrictEqual(L.parseRoute(""), { page: "home" });
  assert.deepStrictEqual(L.parseRoute("#/"), { page: "home" });
  assert.deepStrictEqual(L.parseRoute("#/c/3/5"), { page: "cat", top: 3, sub: 5 });
  assert.deepStrictEqual(L.parseRoute("#/c/3"), { page: "cat", top: 3, sub: 0 });
  assert.deepStrictEqual(L.parseRoute("#/p/a123"), { page: "item", id: "a123" });
  assert.deepStrictEqual(L.parseRoute("#/s/" + encodeURIComponent("洋河 1L")), { page: "search", q: "洋河 1L" });
  assert.deepStrictEqual(L.parseRoute("#/s/"), { page: "search", q: "" });
  assert.deepStrictEqual(L.parseRoute("#/s/%E6"), { page: "search", q: "%E6" });
  assert.deepStrictEqual(L.parseRoute("#/x/1"), { page: "home" });
});

test("formatPrice：千位加逗号，小数照原样", () => {
  assert.strictEqual(L.formatPrice(118), "¥118");
  assert.strictEqual(L.formatPrice(79.9), "¥79.9");
  assert.strictEqual(L.formatPrice(2488), "¥2,488");
  assert.strictEqual(L.formatPrice(1899.5), "¥1,899.5");
  assert.strictEqual(L.formatPrice(12.05), "¥12.05");
});

test("esc 转义 HTML", () => {
  assert.strictEqual(L.esc(`<b>"A&B'</b>`), "&lt;b&gt;&quot;A&amp;B&#39;&lt;/b&gt;");
});

test("imgSrc：大图优先，没有图给占位图", () => {
  assert.strictEqual(L.imgSrc({ it: "img/t/a1-x.jpg", il: "img/l/a1-x.jpg" }, true), "img/l/a1-x.jpg");
  assert.strictEqual(L.imgSrc({ it: "img/t/a1-x.jpg", il: "img/l/a1-x.jpg" }, false), "img/t/a1-x.jpg");
  assert.strictEqual(L.imgSrc({ it: "", il: "" }, true), L.PLACEHOLDER);
  assert.ok(L.PLACEHOLDER.startsWith("data:image/svg+xml"));
});
