# 山姆商品查询 H5 设计

日期：2026-10-15
状态：设计已逐段确认，待审阅本文档

## 1. 目的

用抓到的山姆 App 商品数据做一组手机网页，给店员查商品和价格用。

- 地址：`https://mini.snowmeet.top/sams/`
- 店员用手机打开，几秒内能按名字搜到、或按分类翻到商品，看到图、规格、价格和有没有货。
- 不加登录，知道链接就能打开。数据本来就在公开仓库 `cangjie/sams_scrape` 里。
- 商品数据不放 SQL Server。网页、数据、图片都放 S3 存储桶。
- 以后重新抓了数据，只更新 jsonl 和 S3，不动网页代码、nginx、SnowmeetApi。

## 2. 范围

做：

- 首页：搜索框、数据日期说明、16 个大类入口
- 分类页：左边子分类、右边商品列表
- 搜索
- 商品详情

不做：

- 购物车、收藏、下单、登录、在页面上改数据
- 京东价格：价格只以山姆 App 为准。京东数据只用来给配上对的商品提供高清图。
- 「只在京东有」的 17 个商品：它们没有 App 价格，不放进来。

## 3. 数据来源

都在本仓库 `data/` 下：

| 文件 | 内容 |
|---|---|
| `items.jsonl` | 山姆 App 商品，按分类抓取的记录 5813 条 |
| `jd_items.jsonl` | 京东山姆旗舰店商品 746 个 |
| `jd_images/<商品编号>.jpg` | 京东商品主图 746 张，800×800 |
| `shots/<大类>/<序号>.png` | App 截图 3415 张，452×983 |

商品去重沿用 `scrape.py export` 的规则：同名同价的算同一个商品。5813 条记录合并后是 4604 个商品，分在 16 个大类、160 个子分类下。同一个商品可能挂在多个分类下，每个分类里都要能看到它。

京东配对沿用 `compare.py` 的比对逻辑，约 739 个商品配得上。

## 4. 架构

```
生成（本机）：data/*.jsonl + data/jd_images + data/shots + site/ ──site.py build──→ dist/
发布：        dist/ ──site.py publish（经 mini 服务器）──→ S3 桶 upload/sams/
访问：        手机 → https://mini.snowmeet.top/sams/ → mini 服务器 nginx → img.snowmeet.top（CloudFront）→ S3 upload/sams/
```

组成部分：

| 部分 | 位置 | 做什么 |
|---|---|---|
| 网页源码 | `site/index.html`、`site/app.js`、`site/app.css` | 单页应用，纯 HTML/CSS/JS，不用框架 |
| 生成脚本 | `site.py build` | 读 jsonl，去重、配对，生成数据文件和图片，输出到 `dist/` |
| 裁图 | `site.py` 调用 `bin/analyze` | 从 App 截图里定位商品卡、裁出商品图 |
| 发布脚本 | `site.py publish` | 把 `dist/` 传到 mini 服务器临时目录，再同步进 S3，最后删掉临时目录 |
| 访问入口 | mini 服务器 nginx | 把 `/sams/` 转给 `img.snowmeet.top/upload/sams/` |

`dist/` 是生成结果，不进 Git。

## 5. 页面

单页应用，用地址 `#` 后面的部分切换页面，手机返回键能回到上一页。

| 路由 | 页面 |
|---|---|
| `#/` | 首页 |
| `#/c/<大类序号>/<子分类序号>` | 分类页 |
| `#/s/<关键词>` | 搜索结果 |
| `#/p/<商品 id>` | 商品详情 |

**首页**
- 顶部搜索框。
- 一行小字：「价格为 2026-10-10 山姆 App 快照，仅供参考」。日期从数据文件里取。
- 16 个大类宫格，每格显示商品数。

**分类页**
- 布局照山姆 App：左边一列子分类，右边商品列表。

**商品行**
- 左边缩略图。
- 右边商品名、规格、App 价格（大号红字）。
- 标签「无货」「极速达」。无货的整行变灰，但仍然显示。

**搜索**
- 边输边搜，有短暂延迟。
- 输入按空格分成几个词，每个词都要在商品名、规格、卖点里出现。
- 比较前统一全角半角和大小写。
- 结果平铺，最多显示 200 条，超过时提示「结果太多，请再加一个词」。

**商品详情**
- 大图、商品名、规格、App 价格、标签、卖点。
- 所在分类，含「也在××分类」，可以点进去。
- 数据日期。

**图片加载**
- 列表里的图懒加载。
- 加载失败或没有图时显示占位图。

## 6. 数据文件

生成为 `data/products.<内容指纹>.json`，原始约 1.2 MB，压缩后约 230 KB。网页和数据文件同在 `mini.snowmeet.top/sams/` 下，不涉及跨域。

```json
{
  "meta": { "app_date": "2026-10-10", "generated": "2026-10-15 12:00", "count": 4604 },
  "cats": [
    { "name": "肉蛋果蔬", "subs": [ { "name": "火锅食材", "n": 42 } ] }
  ],
  "items": [
    {
      "id": "a1",
      "n": "澳洲羔羊肉卷",
      "s": "1kg",
      "p": 118.0,
      "d": "甄选澳洲进口羔羊肉，肉质…",
      "t": ["冷冻 进口"],
      "x": 1,
      "o": 0,
      "c": [[0, 3], [0, 5]],
      "it": "img/t/a1-3f2a9c1e.jpg",
      "il": "img/l/a1-3f2a9c1e.jpg"
    }
  ]
}
```

| 字段 | 含义 |
|---|---|
| `id` | 商品 id：`a` + 这个商品在 `items.jsonl` 里最小的 id，重新生成时保持不变 |
| `n` / `s` | 商品名 / 规格，用 `scrape.split_spec` 拆 |
| `p` | App 价格 |
| `d` | 卖点 |
| `t` | 标签 |
| `x` | 极速达：任一分类下标了就算 |
| `o` | 无货：任一分类下标了，或标签里有缺货字样，就算 |
| `c` | 所属分类：`[大类序号, 子分类序号]` 列表，第一个是主分类 |
| `it` / `il` | 缩略图 / 大图路径，相对 `/sams/`。没有图时为空 |

不放进去的字段：识别置信度、截图文件名、抓取时间、京东商品编号和价格。

数据文件名带指纹，每次数据变了文件名就变。生成时把当次的数据文件名（以及 js、css 的文件名）写进 `index.html`；`index.html` 本身不缓存，所以浏览器总能拿到最新的文件名。

## 7. 图片

| 商品 | 来源 | 缩略图 `img/t/` | 大图 `img/l/` |
|---|---|---|---|
| 配上京东的，约 739 个 | `jd_images/<商品编号>.jpg` | 200×200，约 10 KB | 600×600，约 60 KB |
| 其余，约 3865 个 | 从 App 截图裁 | 约 90×90，约 5 KB | 与缩略图同一张 |

- **文件名**：`<商品 id>-<内容指纹前 8 位>.jpg`。图片内容变了文件名就变。
- **总量**：约 70 MB。

**裁图**
- 用 `bin/analyze` 识别截图里的文字，复用 `scrape.py` 里 `analyze` 和 `parse_cards` 的版面规则，找到每张完整露出的商品卡。
- 裁的范围：横向是商品图那一列（版面坐标 x 在 `IMG_X_MIN`～`LIST_X_MIN` 之间），纵向是这张卡的高度。
- 按标题和价格把裁出的图对回商品。同一个商品出现在多张截图里时，取第一张完整露出的。
- `bin/analyze` 是在 ARM 芯片的 Mac mini 上编译的，这台 Intel 笔记本要用 `src/analyze.swift` 重新编译。编译不过就把裁图放到 Mac mini 上跑，其余步骤不受影响。
- 生成后输出一张随机 100 张的总览图，供人工抽查。
- 裁不出来的商品，`it`/`il` 留空，页面显示占位图。脚本最后报告数量。

**增量**：只处理新出现或内容变了的商品，已有的图片不重算。

## 8. 发布

### 8.1 S3

- 桶：`snowmeet-uploads-673751646617-cn-northwest-1-an`，前缀 `upload/sams/`。CloudFront 只放行 `upload/*`，所以必须在这个前缀下。
- 对外地址：`https://img.snowmeet.top/upload/sams/…`

**上传**
- 这台笔记本没有 AWS 凭证。
- 先经美国服务器 2222 转发，把 `dist/` 传到 mini 服务器的临时目录。
- 在 mini 上用实例角色执行 `aws s3 sync --region cn-northwest-1`，设置好内容类型和缓存头。
- 传完删除临时目录。

**缓存头**

| 文件 | Cache-Control |
|---|---|
| `index.html` | `no-cache` |
| 带指纹的 js、css、json、图片 | `public, max-age=31536000, immutable` |

**数据文件压缩**：JSON 先 gzip 压缩，上传时设 `Content-Encoding: gzip`，不依赖 CloudFront 是否开了自动压缩。

**旧文件**：实例角色没有删除权限，换下来的旧文件留在桶里。它们不被引用，不影响使用。

### 8.2 nginx

在 mini 服务器 `mini.snowmeet.top` 的 server 配置里加：

```nginx
location = /sams { return 301 /sams/; }
location = /sams/ {
    proxy_pass https://img.snowmeet.top/upload/sams/index.html;
    proxy_set_header Host img.snowmeet.top;
    proxy_ssl_server_name on;
}
location /sams/ {
    proxy_pass https://img.snowmeet.top/upload/sams/;
    proxy_set_header Host img.snowmeet.top;
    proxy_ssl_server_name on;
}
```

- 改之前备份原配置文件，`nginx -t` 通过后 `reload`。
- 撤回：删掉这三段，`nginx -t`，`reload`。
- **执行前先把实际改动给用户看，用户同意后才改。** 这是生产服务器上唯一的改动，不涉及 SnowmeetApi。

### 8.3 以后更新数据

1. 重新抓取，`items.jsonl` / `jd_items.jsonl` 更新。
2. `python3 site.py build`：重新生成数据文件，只为新的或变了的商品生成图片。
3. `python3 site.py publish`：同步到 S3。

网页代码、nginx、SnowmeetApi 都不用动。

## 9. 测试

**生成脚本自检**（`site.py build` 结束时执行，失败就不产出）
- 商品数等于去重后的数量（当前 4604）。
- 每个商品都有名称、价格和至少一个分类。
- 每个分类的商品数与 `cats` 里的 `n` 一致。
- `it`/`il` 指向的文件在 `dist/` 里都存在。
- 报告：有京东图的数量、裁图成功的数量、没有图的数量。

**网页逻辑**
- 搜索的分词、全角半角和大小写统一、多词同时命中，写成独立函数，用 Node 跑单元测试。

**本地预览**
- 用本机 HTTP 服务预览 `dist/`。
- 在浏览器里切到手机尺寸，走一遍首页、分类切换、搜索（含无结果和结果过多）、详情、返回键、无货商品、没有图的商品。

**上线后**
- 本机连不上 `mini.snowmeet.top`，所以从美国服务器检查：`/sams`、`/sams/`、数据文件、几张图片的状态码和缓存头。
- 请用户用手机实际打开一遍。

## 10. 风险

| 风险 | 应对 |
|---|---|
| 识别程序在 Intel 笔记本上编译不过 | 裁图放到 Mac mini 上跑 |
| 裁图位置偏了或对错商品 | 总览图人工抽查；规则复用抓取时已验证的版面坐标 |
| CloudFront 实际缓存设置不认 `no-cache`，首页更新不及时 | 发布后检查响应头；不行的话请用户在 CloudFront 控制台给 `upload/sams/index.html` 加不缓存规则 |
| 改 nginx 出错影响 `mini.snowmeet.top` | 先备份、`nginx -t` 通过才 `reload`；只新增 `/sams` 开头的规则 |
| mini 服务器磁盘紧张（约 1.9 GB 可用） | 临时目录只放约 70 MB，传完即删 |
